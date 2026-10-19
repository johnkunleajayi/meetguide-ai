//! Windows shared-mode WASAPI. Every COM object remains on its creating thread.
use super::meter::*;
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::SyncSender,
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use wasapi::{
    AudioClient, Device, DeviceEnumerator, DeviceState, Direction, SampleType, StreamMode,
    WaveFormat,
};
use windows::Win32::Media::Audio::{
    IAudioCaptureClient, AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY, AUDCLNT_BUFFERFLAGS_SILENT,
};

struct Apartment;
impl Apartment {
    fn new() -> Result<Self, &'static str> {
        wasapi::initialize_mta()
            .ok()
            .map_err(|_| "Windows audio initialization failed.")?;
        Ok(Self)
    }
}
impl Drop for Apartment {
    fn drop(&mut self) {
        wasapi::deinitialize();
    }
}

pub fn devices() -> Result<Devices, &'static str> {
    let _com = Apartment::new()?;
    let enumerator =
        DeviceEnumerator::new().map_err(|_| "Windows audio service is unavailable.")?;
    Ok(Devices {
        system: enumerate(&enumerator, Direction::Render)?,
        microphones: enumerate(&enumerator, Direction::Capture)?,
    })
}

fn enumerate(
    enumerator: &DeviceEnumerator,
    direction: Direction,
) -> Result<Vec<DeviceInfo>, &'static str> {
    let default = enumerator
        .get_default_device(&direction)
        .ok()
        .and_then(|device| device.get_id().ok());
    let collection = enumerator
        .get_device_collection(&direction)
        .map_err(|_| "Unable to list Windows audio devices. Check Windows Sound settings.")?;
    let count = collection
        .get_nbr_devices()
        .map_err(|_| "Unable to list Windows audio devices.")?;
    let mut devices = Vec::new();
    for index in 0..count {
        // Device removal during enumeration must not hide the remaining devices.
        if let Ok(device) = collection.get_device_at_index(index) {
            if let (Ok(id), Ok(name)) = (device.get_id(), device.get_friendlyname()) {
                devices.push(DeviceInfo {
                    is_default: default.as_ref() == Some(&id),
                    id,
                    name,
                });
            }
        }
    }
    Ok(devices)
}

struct CaptureStream {
    client: AudioClient,
    capture: IAudioCaptureClient,
    device: Device,
    direction: Direction,
    follows_default: bool,
    id: String,
    capacity: u32,
    meter: StreamMeter,
    window: LevelWindow,
}

impl CaptureStream {
    fn open(
        enumerator: &DeviceEnumerator,
        direction: Direction,
        selected: &Option<String>,
    ) -> Result<Self, &'static str> {
        let missing = if direction == Direction::Render {
            "System audio output is unavailable. Select an active playback device in Windows Sound settings."
        } else {
            "Microphone is unavailable. Connect or enable a microphone and refresh devices."
        };
        let device = match selected {
            Some(id) => enumerator.get_device(id),
            None => enumerator.get_default_device(&direction),
        }
        .map_err(|_| missing)?;
        if device.get_direction() != direction
            || device.get_state().map_err(|_| missing)? != DeviceState::Active
        {
            return Err(missing);
        }
        let id = device.get_id().map_err(|_| missing)?;
        let name = device.get_friendlyname().map_err(|_| missing)?;
        let mut client = device.get_iaudioclient().map_err(|_| missing)?;
        let mix = client
            .get_mixformat()
            .map_err(|_| "Unable to read the audio device format.")?;
        let channels = mix.get_nchannels();
        let rate = mix.get_samplespersec();
        if channels == 0 || channels > 32 || rate == 0 || rate > 384_000 {
            return Err("This audio device format is unsupported.");
        }
        let format = WaveFormat::new(
            32,
            32,
            &SampleType::Float,
            rate as usize,
            channels as usize,
            Some(mix.get_dwchannelmask()),
        );
        // Render endpoint + Capture direction sets AUDCLNT_STREAMFLAGS_LOOPBACK.
        let mode = StreamMode::PollingShared {
            autoconvert: true,
            buffer_duration_hns: 1_000_000,
        };
        let startup_error = if direction == Direction::Render {
            "Unable to start system audio. Check the output device and close applications using exclusive audio mode."
        } else {
            "Unable to start the microphone. Check Windows Settings > Privacy & security > Microphone, including desktop app access, and close exclusive audio applications."
        };
        client
            .initialize_client(&format, &Direction::Capture, &mode)
            .map_err(|_| startup_error)?;
        let capacity = client.get_buffer_size().map_err(|_| startup_error)?;
        if capacity == 0 || capacity > 384_000 {
            return Err("Windows returned an unsupported audio buffer size.");
        }
        // Read the native packet directly so AUDCLNT_BUFFERFLAGS_SILENT may safely
        // have a null data pointer. Never dereference silent packets or copy PCM to IPC.
        let capture = unsafe { client.as_iaudioclient().GetService::<IAudioCaptureClient>() }
            .map_err(|_| startup_error)?;
        let stream = Self {
            client,
            capture,
            device,
            direction,
            follows_default: selected.is_none(),
            id,
            capacity,
            meter: StreamMeter {
                device_name: name,
                sample_rate: rate,
                channels,
                ..Default::default()
            },
            window: LevelWindow::default(),
        };
        stream.client.start_stream().map_err(|_| startup_error)?;
        Ok(stream)
    }

    fn drain(&mut self, stop: &AtomicBool) -> Result<(), &'static str> {
        for _ in 0..64 {
            if stop.load(Ordering::Acquire) {
                break;
            }
            let available =
                unsafe { self.capture.GetNextPacketSize() }.map_err(|_| self.capture_error())?;
            if available == 0 {
                break;
            }
            let mut data = std::ptr::null_mut();
            let mut frames = 0;
            let mut flags = 0;
            unsafe {
                self.capture
                    .GetBuffer(&mut data, &mut frames, &mut flags, None, None)
            }
            .map_err(|_| self.capture_error())?;
            let packet = Packet {
                client: &self.capture,
                frames,
            };
            let silent = flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0;
            let length = frames as usize * self.meter.channels as usize * 4;
            if frames > self.capacity || (!silent && frames > 0 && data.is_null()) {
                return Err("Windows returned an invalid audio packet. Stop and restart capture.");
            }
            let bytes = if silent || frames == 0 {
                &[]
            } else {
                // SAFETY: WASAPI owns this buffer until ReleaseBuffer. The requested
                // format is interleaved f32 PCM and frames are bounded above.
                unsafe { std::slice::from_raw_parts(data, length) }
            };
            self.window.consume(
                AudioFrame {
                    bytes,
                    frames,
                    channels: self.meter.channels,
                    silent,
                    discontinuity: flags & AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY.0 as u32 != 0,
                },
                &mut self.meter,
            );
            packet.release().map_err(|_| self.capture_error())?;
        }
        Ok(())
    }

    fn capture_error(&self) -> &'static str {
        if self.direction == Direction::Render {
            "System audio stopped or the output device changed. Refresh devices and restart the session."
        } else {
            "Microphone capture stopped. Check its connection and Windows microphone permissions, then restart the session."
        }
    }

    fn check_device(&self, enumerator: &DeviceEnumerator) -> Result<(), &'static str> {
        if self.device.get_state().map_err(|_| self.capture_error())? != DeviceState::Active {
            return Err(self.capture_error());
        }
        if self.follows_default {
            let current = enumerator
                .get_default_device(&self.direction)
                .and_then(|device| device.get_id())
                .map_err(|_| self.capture_error())?;
            if current != self.id {
                return Err("The Windows default audio device changed. Refresh devices and restart to use the new device.");
            }
        }
        Ok(())
    }
}

impl Drop for CaptureStream {
    fn drop(&mut self) {
        let _ = self.client.stop_stream();
    }
}
struct Packet<'a> {
    client: &'a IAudioCaptureClient,
    frames: u32,
}
impl Packet<'_> {
    fn release(mut self) -> windows::core::Result<()> {
        let frames = std::mem::take(&mut self.frames);
        if frames > 0 {
            unsafe { self.client.ReleaseBuffer(frames) }
        } else {
            Ok(())
        }
    }
}
impl Drop for Packet<'_> {
    fn drop(&mut self) {
        if self.frames > 0 {
            let _ = unsafe { self.client.ReleaseBuffer(self.frames) };
        }
    }
}

pub fn run(
    options: CaptureOptions,
    stop: Arc<AtomicBool>,
    snapshot: Arc<Mutex<CaptureStatus>>,
    ready: SyncSender<Result<(), &'static str>>,
) -> Result<(), &'static str> {
    let _com = Apartment::new()?;
    let enumerator =
        DeviceEnumerator::new().map_err(|_| "Windows audio service is unavailable.")?;
    let mut system = if options.mode.system() {
        Some(CaptureStream::open(
            &enumerator,
            Direction::Render,
            &options.system_device_id,
        )?)
    } else {
        None
    };
    let mut microphone = if options.mode.microphone() {
        Some(CaptureStream::open(
            &enumerator,
            Direction::Capture,
            &options.microphone_device_id,
        )?)
    } else {
        None
    };
    let mut publish = Instant::now();
    let mut device_check = Instant::now();
    let update = |system: &Option<CaptureStream>, microphone: &Option<CaptureStream>| {
        if let Ok(mut state) = snapshot.lock() {
            *state = CaptureStatus {
                state: CaptureState::Listening,
                system: system.as_ref().map(|s| s.meter.clone()),
                microphone: microphone.as_ref().map(|s| s.meter.clone()),
                error: None,
            };
        }
    };
    update(&system, &microphone);
    let _ = ready.send(Ok(()));
    while !stop.load(Ordering::Acquire) {
        for stream in [&mut system, &mut microphone].into_iter().flatten() {
            stream.drain(&stop)?;
            if device_check.elapsed() >= Duration::from_millis(500) {
                stream.check_device(&enumerator)?;
            }
        }
        if device_check.elapsed() >= Duration::from_millis(500) {
            device_check = Instant::now();
        }
        if publish.elapsed() >= Duration::from_millis(100) {
            for stream in [&mut system, &mut microphone].into_iter().flatten() {
                stream.window.flush(&mut stream.meter);
            }
            update(&system, &microphone);
            publish = Instant::now();
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    Ok(())
}
