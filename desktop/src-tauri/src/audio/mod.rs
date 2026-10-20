pub(crate) mod meter;
#[cfg(target_os = "windows")]
mod windows;

pub use meter::{CaptureOptions, CaptureState, CaptureStatus, Devices};
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::Duration,
};
use tauri::State;

struct Worker {
    stop: Arc<AtomicBool>,
    handle: JoinHandle<()>,
}
#[derive(Default)]
pub struct AudioService {
    pub(crate) cues: Arc<crate::cue::CueService>,
    pub(crate) transcript: Arc<Mutex<crate::transcription::TranscriptStore>>,
    operation: Mutex<()>,
    worker: Mutex<Option<Worker>>,
    snapshot: Arc<Mutex<CaptureStatus>>,
}

impl AudioService {
    pub fn clear_transcript(&self) {
        self.cues.reset(None);
        if let Ok(mut store) = self.transcript.lock() {
            store.reset(&[]);
        }
    }

    pub fn status(&self) -> Result<CaptureStatus, &'static str> {
        self.snapshot
            .lock()
            .map(|state| state.clone())
            .map_err(|_| "Audio state is unavailable. Restart MeetGuide.")
    }

    fn start(
        &self,
        options: CaptureOptions,
        authorize: impl FnOnce() -> Result<Option<crate::transcription::RelayConfig>, &'static str>,
    ) -> Result<CaptureStatus, &'static str> {
        let _operation = self
            .operation
            .lock()
            .map_err(|_| "Audio control is unavailable.")?;
        let relay = authorize()?;
        let mut worker = self
            .worker
            .lock()
            .map_err(|_| "Audio control is unavailable.")?;
        if worker.as_ref().is_some_and(|job| !job.handle.is_finished()) {
            return Err("Audio capture is already running.");
        }
        if let Some(previous) = worker.take() {
            let _ = previous.handle.join();
        }
        let sources = [
            options
                .mode
                .system()
                .then_some(crate::transcription::Source::System),
            options
                .mode
                .microphone()
                .then_some(crate::transcription::Source::Microphone),
        ]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
        let transcript = self.transcript.clone();
        let session_id = {
            let mut store = transcript
                .lock()
                .map_err(|_| "Transcript state is unavailable.")?;
            store.reset(if relay.is_some() { &sources } else { &[] });
            store.snapshot.session_id
        };
        self.cues.reset(relay.as_ref().map(|_| session_id));
        if relay.is_some() {
            crate::cue::start(transcript.clone(), self.cues.clone());
        }
        let cues = self.cues.clone();
        let stop = Arc::new(AtomicBool::new(false));
        let thread_stop = stop.clone();
        let snapshot = self.snapshot.clone();
        *snapshot.lock().map_err(|_| "Audio state is unavailable.")? = CaptureStatus {
            state: CaptureState::Starting,
            ..Default::default()
        };
        let (ready, receiver) = mpsc::sync_channel(2);
        let handle = thread::Builder::new()
            .name("meetguide-audio".into())
            .spawn(move || {
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    #[cfg(target_os = "windows")]
                    {
                        windows::run(
                            options,
                            thread_stop,
                            snapshot.clone(),
                            ready.clone(),
                            relay,
                            transcript.clone(),
                        )
                    }
                    #[cfg(not(target_os = "windows"))]
                    {
                        let _ = (options, thread_stop);
                        Err("Live audio capture currently supports Windows only.")
                    }
                }))
                .unwrap_or(Err(
                    "The audio worker stopped unexpectedly. Restart the session.",
                ));
                if let Err(message) = result {
                    cues.reset(None);
                    if let Ok(mut store) = transcript.lock() {
                        for source in [
                            crate::transcription::Source::System,
                            crate::transcription::Source::Microphone,
                        ] {
                            store.state(source, "error", Some(message), 0);
                        }
                    }
                    if let Ok(mut state) = snapshot.lock() {
                        *state = CaptureStatus {
                            state: CaptureState::Error,
                            error: Some(message.into()),
                            ..Default::default()
                        };
                    }
                    let _ = ready.send(Err(message));
                }
            })
            .map_err(|_| {
                self.cues.reset(None);
                if let Ok(mut store) = self.transcript.lock() {
                    store.stop_understanding();
                }
                if let Ok(mut state) = self.snapshot.lock() {
                    *state = CaptureStatus {
                        state: CaptureState::Error,
                        error: Some("Unable to start the Windows audio worker.".into()),
                        ..Default::default()
                    };
                }
                "Unable to start the Windows audio worker."
            })?;
        *worker = Some(Worker { stop, handle });
        match receiver.recv_timeout(Duration::from_secs(15)) {
            Ok(Ok(())) => self.status(),
            outcome => {
                self.cues.reset(None);
                if let Ok(mut store) = self.transcript.lock() {
                    store.stop_understanding();
                }
                if let Some(job) = worker.take() {
                    job.stop.store(true, Ordering::Release);
                    let _ = job.handle.join();
                }
                let message = match outcome {
                    Ok(Err(message)) => message,
                    _ => "Windows audio startup timed out. Check your devices and retry.",
                };
                *self
                    .snapshot
                    .lock()
                    .map_err(|_| "Audio state is unavailable.")? = CaptureStatus {
                    state: CaptureState::Error,
                    error: Some(message.into()),
                    ..Default::default()
                };
                Err(message)
            }
        }
    }

    pub fn stop(&self) -> Result<(), &'static str> {
        self.stop_with(|| Ok(()))
    }

    pub fn stop_with(
        &self,
        after: impl FnOnce() -> Result<(), &'static str>,
    ) -> Result<(), &'static str> {
        let _operation = self
            .operation
            .lock()
            .map_err(|_| "Audio control is unavailable.")?;
        self.cues.reset(None);
        if let Ok(mut store) = self.transcript.lock() {
            store.stop_understanding();
        }
        if let Some(worker) = self
            .worker
            .lock()
            .map_err(|_| "Audio control is unavailable.")?
            .take()
        {
            worker.stop.store(true, Ordering::Release);
            let _ = worker.handle.join();
        }
        *self
            .snapshot
            .lock()
            .map_err(|_| "Audio state is unavailable.")? = CaptureStatus::default();
        after()
    }
}
impl Drop for AudioService {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

#[tauri::command]
pub async fn audio_devices() -> Result<Devices, String> {
    tauri::async_runtime::spawn_blocking(|| {
        #[cfg(target_os = "windows")]
        {
            windows::devices()
        }
        #[cfg(not(target_os = "windows"))]
        {
            Err("Live audio capture currently supports Windows only.")
        }
    })
    .await
    .map_err(|_| "Audio device enumeration failed.".to_owned())?
    .map_err(str::to_owned)
}

#[tauri::command]
pub async fn audio_start(
    options: CaptureOptions,
    audio: State<'_, Arc<AudioService>>,
    auth: State<'_, Arc<crate::auth::AuthService>>,
) -> Result<CaptureStatus, String> {
    let audio = audio.inner().clone();
    let auth = auth.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        // Reuse the existing session validation; no new authentication mechanism.
        audio.start(options, || {
            if auth.restore()?.is_none() {
                return Err("Sign in to MeetGuide before starting audio capture.");
            }
            let token = crate::vault::load()?.ok_or("Sign in before starting transcription.")?;
            Ok(Some(crate::transcription::RelayConfig {
                url: crate::api::Api::new()?.transcription_url(),
                token,
            }))
        })
    })
    .await
    .map_err(|_| "Audio startup failed.".to_owned())?
    .map_err(str::to_owned)
}

#[tauri::command]
pub fn audio_status(audio: State<'_, Arc<AudioService>>) -> Result<CaptureStatus, String> {
    audio.status().map_err(str::to_owned)
}

#[tauri::command]
pub async fn audio_stop(audio: State<'_, Arc<AudioService>>) -> Result<(), String> {
    let audio = audio.inner().clone();
    tauri::async_runtime::spawn_blocking(move || audio.stop())
        .await
        .map_err(|_| "Unable to stop audio capture.".to_owned())?
        .map_err(str::to_owned)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stopping_is_idempotent_and_resets_activity() {
        let service = AudioService::default();
        service.snapshot.lock().unwrap().state = CaptureState::Error;
        service.stop().unwrap();
        service.stop().unwrap();
        assert!(service.status().unwrap().state == CaptureState::Idle);
        assert!(service.status().unwrap().system.is_none());
    }
    #[test]
    fn stop_joins_worker_before_returning() {
        let service = AudioService::default();
        let stop = Arc::new(AtomicBool::new(false));
        let flag = stop.clone();
        let exited = Arc::new(AtomicBool::new(false));
        let thread_exited = exited.clone();
        let handle = thread::spawn(move || {
            while !flag.load(Ordering::Acquire) {
                thread::sleep(Duration::from_millis(1));
            }
            thread_exited.store(true, Ordering::Release);
        });
        *service.worker.lock().unwrap() = Some(Worker { stop, handle });
        service.stop().unwrap();
        assert!(exited.load(Ordering::Acquire));
        assert!(service.worker.lock().unwrap().is_none());
    }
    #[test]
    fn rejected_authentication_never_starts_a_worker() {
        let service = AudioService::default();
        let options = CaptureOptions {
            mode: meter::Mode::Both,
            system_device_id: None,
            microphone_device_id: None,
        };
        assert!(service.start(options, || Err("Sign in required")).is_err());
        assert!(service.worker.lock().unwrap().is_none());
        assert!(service.status().unwrap().state == CaptureState::Idle);
    }
    #[test]
    fn logout_action_runs_after_capture_is_stopped_even_when_logout_fails() {
        let service = AudioService::default();
        let result = service.stop_with(|| {
            assert!(service.status().unwrap().state == CaptureState::Idle);
            assert!(service.worker.lock().unwrap().is_none());
            Err("Logout temporarily unavailable")
        });
        assert!(result.is_err());
        assert!(service.status().unwrap().state == CaptureState::Idle);
    }
    #[test]
    fn logout_clears_conversation_and_events_after_stopping_processing() {
        let service = AudioService::default();
        {
            let mut store = service.transcript.lock().unwrap();
            store.reset(&[crate::transcription::Source::System]);
            store.event(
                crate::transcription::Source::System,
                1,
                1,
                0,
                "Tell me about yourself.",
                true,
            );
            assert_eq!(store.snapshot.understanding.turns.len(), 1);
        }
        service
            .stop_with(|| {
                assert!(
                    !service
                        .transcript
                        .lock()
                        .unwrap()
                        .snapshot
                        .understanding
                        .active
                );
                service.clear_transcript();
                Ok(())
            })
            .unwrap();
        let store = service.transcript.lock().unwrap();
        assert!(store.snapshot.entries.is_empty());
        assert!(store.snapshot.understanding.turns.is_empty());
        assert!(store.snapshot.understanding.events.is_empty());
    }
    #[cfg(target_os = "windows")]
    #[test]
    #[ignore = "Opt-in: opens real Windows audio devices briefly; never writes or uploads audio"]
    fn windows_hardware_capture_smoke() {
        let devices = windows::devices().expect("Windows device enumeration failed");
        assert!(
            !devices.system.is_empty(),
            "No active system audio output device"
        );
        assert!(!devices.microphones.is_empty(), "No active microphone");
        let service = AudioService::default();
        for mode in [
            meter::Mode::System,
            meter::Mode::Microphone,
            meter::Mode::Both,
        ] {
            let status = service
                .start(
                    CaptureOptions {
                        mode,
                        system_device_id: None,
                        microphone_device_id: None,
                    },
                    || Ok(None),
                )
                .expect("Audio startup failed");
            assert!(status.state == CaptureState::Listening);
            assert_eq!(status.system.is_some(), mode.system());
            assert_eq!(status.microphone.is_some(), mode.microphone());
            thread::sleep(Duration::from_millis(700));
            assert!(
                service.status().unwrap().state == CaptureState::Listening,
                "Device error during capture"
            );
            if let Some(microphone) = service.status().unwrap().microphone {
                assert!(microphone.frames > 0, "Microphone returned no PCM frames");
            }
            service.stop().unwrap();
            assert!(service.status().unwrap().state == CaptureState::Idle);
        }
    }
}
