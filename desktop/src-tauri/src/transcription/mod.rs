mod pcm;
mod relay;
mod store;
use crate::audio::meter::AudioFrame;
pub use relay::RelayConfig;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc, Mutex,
};
pub use store::{Snapshot, Source, TranscriptStore};
use tokio::sync::{mpsc, watch};

pub struct AudioPort {
    converter: pcm::PcmConverter,
    port: Arc<relay::PortState>,
    rate: u32,
}
impl AudioPort {
    pub fn feed(&mut self, frame: AudioFrame<'_>) {
        if !self.port.accepting.load(Ordering::Acquire) {
            self.converter.reset();
            return;
        }
        if frame.discontinuity {
            self.converter.reset();
        }
        let port = &self.port;
        let result = self
            .converter
            .feed(frame.bytes, frame.frames, frame.silent, |chunk| {
                if port.sender.try_send(chunk).is_err() {
                    port.dropped.fetch_add(1, Ordering::Relaxed);
                    port.accepting.store(false, Ordering::Release);
                    port.gap.store(true, Ordering::Release);
                }
            });
        if result.is_err() {
            self.port.gap.store(true, Ordering::Release);
        }
    }
    pub fn finish(&mut self) {
        self.feed(AudioFrame {
            bytes: &[],
            frames: self.rate / 10,
            channels: 1,
            silent: true,
            discontinuity: false,
        });
    }
}

pub struct Session {
    ports: Vec<(Source, Arc<relay::PortState>)>,
    stop: watch::Sender<bool>,
    thread: Option<std::thread::JoinHandle<()>>,
}
impl Session {
    pub fn new(
        config: RelayConfig,
        sources: &[Source],
        store: Arc<Mutex<TranscriptStore>>,
    ) -> Result<Self, &'static str> {
        let (stop, receiver) = watch::channel(false);
        let mut ports = Vec::new();
        let mut workers = Vec::new();
        for source in sources {
            let (sender, audio) = mpsc::channel(50);
            let port = Arc::new(relay::PortState {
                sender,
                accepting: AtomicBool::new(false),
                gap: AtomicBool::new(false),
                dropped: AtomicU64::new(0),
            });
            ports.push((*source, port.clone()));
            workers.push((
                config.clone(),
                *source,
                port,
                audio,
                receiver.clone(),
                store.clone(),
            ));
        }
        let thread = std::thread::Builder::new()
            .name("meetguide-transcription".into())
            .spawn(move || {
                let runtime = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build();
                if let Ok(runtime) = runtime {
                    runtime.block_on(async {
                        let tasks = workers.into_iter().map(
                            |(config, source, port, audio, stop, store)| {
                                tokio::spawn(relay::run(config, source, port, audio, stop, store))
                            },
                        );
                        let _ = futures_util::future::join_all(tasks).await;
                    });
                } else if let Ok(mut store) = store.lock() {
                    for source in [Source::System, Source::Microphone] {
                        store.state(
                            source,
                            "error",
                            Some("Unable to start transcription networking."),
                            0,
                        );
                    }
                }
            })
            .map_err(|_| "Unable to start transcription networking.")?;
        Ok(Self {
            ports,
            stop,
            thread: Some(thread),
        })
    }
    pub fn port(
        &self,
        source: Source,
        rate: u32,
        channels: u16,
    ) -> Result<AudioPort, &'static str> {
        let port = self
            .ports
            .iter()
            .find(|(value, _)| *value == source)
            .ok_or("Missing audio transcription source.")?
            .1
            .clone();
        Ok(AudioPort {
            converter: pcm::PcmConverter::new(rate, channels)?,
            port,
            rate,
        })
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        for (_, port) in &self.ports {
            port.accepting.store(false, Ordering::Release);
        }
        let _ = self.stop.send(true);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

#[tauri::command]
pub fn transcription_status(
    after: u64,
    audio: tauri::State<'_, Arc<crate::audio::AudioService>>,
) -> Result<Option<Snapshot>, String> {
    let store = audio
        .transcript
        .lock()
        .map_err(|_| "Transcript state is unavailable.".to_owned())?;
    Ok((store.snapshot.version != after).then(|| store.snapshot.clone()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures_util::{SinkExt, StreamExt};
    use std::time::{Duration, Instant};
    use tokio_tungstenite::{
        accept_hdr_async,
        tungstenite::{
            handshake::server::{Request, Response},
            Message,
        },
    };

    #[test]
    fn native_streams_keep_sources_separate_and_flush_final_results_on_stop() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        listener.set_nonblocking(true).unwrap();
        let server = std::thread::spawn(move || {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap();
            runtime.block_on(async move {
                let listener = tokio::net::TcpListener::from_std(listener).unwrap();
                let mut workers = Vec::new();
                for _ in 0..2 {
                    let (stream, _) = tokio::time::timeout(Duration::from_secs(8), listener.accept()).await.unwrap().unwrap();
                    workers.push(tokio::spawn(async move {
                        let mut socket = accept_hdr_async(stream, |request: &Request, response: Response| {
                            assert!(request.headers().get("authorization").is_some());
                            assert!(request.uri().query().unwrap().contains("source="));
                            Ok(response)
                        }).await.unwrap();
                        socket.send(Message::Text("{\"type\":\"ready\"}".into())).await.unwrap();
                        loop {
                            let incoming = tokio::time::timeout(Duration::from_secs(8), socket.next()).await.unwrap().unwrap().unwrap();
                            match incoming {
                                Message::Binary(bytes) => {
                                    assert_eq!(bytes.len(), 640);
                                    socket.send(Message::Text("{\"type\":\"transcript\",\"segment\":0,\"text\":\"Sample\",\"final\":false}".into())).await.unwrap();
                                }
                                Message::Text(text) if text.contains("finish") => {
                                    socket.send(Message::Text("{\"type\":\"transcript\",\"segment\":0,\"text\":\"Sample final.\",\"final\":true}".into())).await.unwrap();
                                    socket.send(Message::Text("{\"type\":\"done\"}".into())).await.unwrap();
                                    break;
                                }
                                _ => {}
                            }
                        }
                    }));
                }
                for worker in workers { worker.await.unwrap(); }
            });
        });
        let store = Arc::new(Mutex::new(TranscriptStore::default()));
        let sources = [Source::System, Source::Microphone];
        store.lock().unwrap().reset(&sources);
        let session = Session::new(
            RelayConfig {
                url: format!("ws://{address}/api/transcription/stream"),
                token: zeroize::Zeroizing::new("test-only-native-token".into()),
            },
            &sources,
            store.clone(),
        )
        .unwrap();
        let deadline = Instant::now() + Duration::from_secs(8);
        while !store
            .lock()
            .unwrap()
            .snapshot
            .streams
            .iter()
            .all(|stream| stream.state == "streaming")
        {
            assert!(Instant::now() < deadline, "Native relay did not connect");
            std::thread::sleep(Duration::from_millis(10));
        }
        let mut ports: Vec<_> = sources
            .iter()
            .map(|source| session.port(*source, 48000, 2).unwrap())
            .collect();
        for port in &mut ports {
            port.feed(AudioFrame {
                bytes: &[],
                frames: 9600,
                channels: 2,
                silent: true,
                discontinuity: false,
            });
        }
        while store.lock().unwrap().snapshot.entries.len() < 2 {
            assert!(
                Instant::now() < deadline,
                "Native relay did not return both sources"
            );
            std::thread::sleep(Duration::from_millis(10));
        }
        drop(ports);
        drop(session);
        server.join().unwrap();
        let store = store.lock().unwrap();
        assert_eq!(store.snapshot.entries.len(), 2);
        assert!(store.snapshot.entries.iter().all(|entry| entry.final_text));
        assert!(store
            .snapshot
            .streams
            .iter()
            .all(|stream| stream.state == "stopped"));
    }
    #[test]
    fn bounded_ingress_signals_a_gap_instead_of_accumulating_audio() {
        let (sender, _receiver) = mpsc::channel(1);
        let shared = Arc::new(relay::PortState {
            sender,
            accepting: AtomicBool::new(true),
            gap: AtomicBool::new(false),
            dropped: AtomicU64::new(0),
        });
        let mut port = AudioPort {
            converter: pcm::PcmConverter::new(48000, 1).unwrap(),
            port: shared.clone(),
            rate: 48000,
        };
        port.feed(AudioFrame {
            bytes: &[],
            frames: 9600,
            channels: 1,
            silent: true,
            discontinuity: false,
        });
        assert!(shared.gap.load(Ordering::Acquire));
        assert!(!shared.accepting.load(Ordering::Acquire));
        assert!(shared.dropped.load(Ordering::Relaxed) > 0);
    }
}

#[cfg(test)]
mod reconnect_tests {
    use super::*;
    use futures_util::{SinkExt, StreamExt};
    use std::time::{Duration, Instant};
    use tokio_tungstenite::{accept_async, tungstenite::Message};
    #[test]
    fn transient_disconnect_reconnects_without_overwriting_old_partial() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        listener.set_nonblocking(true).unwrap();
        let server = std::thread::spawn(move || {
            tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
                let listener = tokio::net::TcpListener::from_std(listener).unwrap();
                for attempt in 0..2 {
                    let (stream, _) = tokio::time::timeout(Duration::from_secs(8), listener.accept()).await.unwrap().unwrap();
                    let mut socket = accept_async(stream).await.unwrap();
                    socket.send(Message::Text("{\"type\":\"ready\"}".into())).await.unwrap();
                    let text = if attempt == 0 { "{\"type\":\"transcript\",\"segment\":0,\"text\":\"Before gap\",\"final\":false}" } else { "{\"type\":\"transcript\",\"segment\":0,\"text\":\"After gap\",\"final\":true}" };
                    socket.send(Message::Text(text.into())).await.unwrap();
                    if attempt == 0 { let _ = socket.close(None).await; continue; }
                    while let Some(Ok(incoming)) = tokio::time::timeout(Duration::from_secs(8), socket.next()).await.unwrap() {
                        if let Message::Text(text) = incoming { if text.contains("finish") {
                            let _ = socket.send(Message::Text("{\"type\":\"done\"}".into())).await; break;
                        } }
                    }
                }
            });
        });
        let store = Arc::new(Mutex::new(TranscriptStore::default()));
        store.lock().unwrap().reset(&[Source::System]);
        let session = Session::new(
            RelayConfig {
                url: format!("ws://{address}/stream"),
                token: zeroize::Zeroizing::new("test-only".into()),
            },
            &[Source::System],
            store.clone(),
        )
        .unwrap();
        let deadline = Instant::now() + Duration::from_secs(8);
        loop {
            if store
                .lock()
                .unwrap()
                .snapshot
                .entries
                .iter()
                .any(|entry| entry.final_text)
            {
                break;
            }
            assert!(Instant::now() < deadline, "Transcription did not reconnect");
            std::thread::sleep(Duration::from_millis(10));
        }
        drop(session);
        server.join().unwrap();
        let store = store.lock().unwrap();
        assert_eq!(store.snapshot.entries.len(), 2);
        assert!(store.snapshot.entries[0].interrupted);
        assert!(store.snapshot.entries[1].final_text);
    }
}
