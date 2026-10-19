//! In-memory frame boundary. Audio never crosses IPC; only aggregate meters do.
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    System,
    Microphone,
    Both,
}

impl Mode {
    pub fn system(self) -> bool {
        matches!(self, Self::System | Self::Both)
    }
    pub fn microphone(self) -> bool {
        matches!(self, Self::Microphone | Self::Both)
    }
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CaptureOptions {
    pub mode: Mode,
    pub system_device_id: Option<String>,
    pub microphone_device_id: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DeviceInfo {
    pub id: String,
    pub name: String,
    pub is_default: bool,
}

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Devices {
    pub system: Vec<DeviceInfo>,
    pub microphones: Vec<DeviceInfo>,
}

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StreamMeter {
    pub device_name: String,
    pub rms: f32,
    pub peak: f32,
    pub frames: u64,
    pub sample_rate: u32,
    pub channels: u16,
    pub discontinuities: u64,
}

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureStatus {
    pub state: CaptureState,
    pub system: Option<StreamMeter>,
    pub microphone: Option<StreamMeter>,
    pub error: Option<String>,
}

#[derive(Clone, Copy, Default, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureState {
    #[default]
    Idle,
    Starting,
    Listening,
    Error,
}

/// A borrowed interleaved f32 PCM packet, valid only during synchronous consumption.
/// A future transcription consumer belongs here, with an explicitly bounded queue.
pub struct AudioFrame<'a> {
    pub bytes: &'a [u8],
    pub frames: u32,
    pub channels: u16,
    pub silent: bool,
    pub discontinuity: bool,
}

#[derive(Default)]
pub struct LevelWindow {
    sum: f64,
    samples: u64,
    peak: f32,
}

impl LevelWindow {
    pub fn consume(&mut self, frame: AudioFrame<'_>, meter: &mut StreamMeter) {
        meter.frames = meter.frames.saturating_add(u64::from(frame.frames));
        meter.discontinuities += u64::from(frame.discontinuity);
        let count = u64::from(frame.frames) * u64::from(frame.channels);
        if frame.silent {
            self.samples += count;
            return;
        }
        for bytes in frame.bytes.chunks_exact(4).take(count as usize) {
            let value = f32::from_le_bytes(bytes.try_into().expect("four-byte sample"));
            let value = if value.is_finite() {
                value.clamp(-1.0, 1.0)
            } else {
                0.0
            };
            self.sum += f64::from(value) * f64::from(value);
            self.samples += 1;
            self.peak = self.peak.max(value.abs());
        }
    }

    pub fn flush(&mut self, meter: &mut StreamMeter) {
        meter.rms = if self.samples == 0 {
            0.0
        } else {
            (self.sum / self.samples as f64).sqrt() as f32
        };
        meter.peak = self.peak;
        *self = Self::default();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn feed(values: &[f32], silent: bool) -> StreamMeter {
        let bytes: Vec<_> = values
            .iter()
            .flat_map(|value| value.to_le_bytes())
            .collect();
        let mut meter = StreamMeter::default();
        let mut window = LevelWindow::default();
        window.consume(
            AudioFrame {
                bytes: &bytes,
                frames: values.len() as u32,
                channels: 1,
                silent,
                discontinuity: true,
            },
            &mut meter,
        );
        window.flush(&mut meter);
        meter
    }
    #[test]
    fn rms_peak_and_frame_counts_are_measured_from_pcm() {
        let meter = feed(&[0.5, -0.5, 0.5, -0.5], false);
        assert!((meter.rms - 0.5).abs() < 0.00001);
        assert_eq!(meter.peak, 0.5);
        assert_eq!(meter.frames, 4);
        assert_eq!(meter.discontinuities, 1);
    }
    #[test]
    fn silence_flags_override_buffer_contents_and_nonfinite_values_are_safe() {
        assert_eq!(feed(&[1.0, -1.0], true).peak, 0.0);
        let meter = feed(&[f32::NAN, f32::INFINITY, -3.0], false);
        assert!(meter.rms.is_finite() && meter.rms <= 1.0);
        assert_eq!(meter.peak, 1.0);
    }
    #[test]
    fn a_window_without_packets_returns_to_zero_instead_of_showing_stale_activity() {
        let mut window = LevelWindow::default();
        let mut meter = StreamMeter {
            rms: 0.8,
            peak: 1.0,
            ..Default::default()
        };
        window.flush(&mut meter);
        assert_eq!(meter.rms, 0.0);
        assert_eq!(meter.peak, 0.0);
    }
    #[test]
    fn modes_select_exactly_the_requested_sources() {
        assert!(Mode::System.system() && !Mode::System.microphone());
        assert!(Mode::Microphone.microphone() && !Mode::Microphone.system());
        assert!(Mode::Both.system() && Mode::Both.microphone());
        assert!(serde_json::from_str::<Mode>("\"invalid\"").is_err());
    }
}
