use super::store::{Source, TranscriptStore};
use futures_util::{SinkExt, StreamExt};
use std::{
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tokio::sync::{mpsc, watch};
use tokio_tungstenite::{
    connect_async,
    tungstenite::{client::IntoClientRequest, Message},
};
use zeroize::Zeroizing;

#[derive(Clone)]
pub struct RelayConfig {
    pub url: String,
    pub token: Zeroizing<String>,
}
pub struct PortState {
    pub sender: mpsc::Sender<Vec<u8>>,
    pub accepting: AtomicBool,
    pub gap: AtomicBool,
    pub dropped: AtomicU64,
}
pub fn state(
    store: &Arc<Mutex<TranscriptStore>>,
    source: Source,
    value: &str,
    message: Option<&str>,
    port: &PortState,
) {
    if let Ok(mut store) = store.lock() {
        store.state(source, value, message, port.dropped.load(Ordering::Relaxed));
    }
}

pub async fn run(
    config: RelayConfig,
    source: Source,
    port: Arc<PortState>,
    mut audio: mpsc::Receiver<Vec<u8>>,
    mut stop: watch::Receiver<bool>,
    store: Arc<Mutex<TranscriptStore>>,
) {
    let began = Instant::now();
    let mut epoch = 0u64;
    let mut attempts = 0u32;
    loop {
        if *stop.borrow() {
            break;
        }
        epoch += 1;
        while audio.try_recv().is_ok() {}
        port.gap.store(false, Ordering::Release);
        let mut base_ms = began.elapsed().as_millis() as u64;
        let mut url = match url::Url::parse(&config.url) {
            Ok(url) => url,
            Err(_) => break,
        };
        url.query_pairs_mut().append_pair("source", source.wire());
        let mut request = match url.as_str().into_client_request() {
            Ok(request) => request,
            Err(_) => break,
        };
        let header = match format!("Bearer {}", config.token.as_str()).parse() {
            Ok(header) => header,
            Err(_) => break,
        };
        request.headers_mut().insert("Authorization", header);
        let mut socket = tokio::select! {
            _ = stop.changed() => break,
            result = tokio::time::timeout(Duration::from_secs(10), connect_async(request)) => {
                match result { Ok(Ok((socket, _))) => socket, _ => {
                    state(&store, source, "reconnecting", Some("Cannot reach transcription. Check the backend connection; speech during this gap is not buffered."), &port);
                    attempts += 1;
                    if wait_retry(&mut stop, attempts).await { break; }
                    continue;
                } }
            }
        };
        let mut ready = false;
        let mut retryable = true;
        let mut message =
            "Transcription disconnected. Reconnecting; some speech may be missing.".to_owned();
        let mut tick = tokio::time::interval(Duration::from_millis(20));
        tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut last_audio = Instant::now();
        let connected_at = Instant::now();
        let mut stopping = false;
        let mut stop_deadline = Instant::now();
        loop {
            tokio::select! {
                biased;
                _ = stop.changed(), if !stopping => {
                    port.accepting.store(false, Ordering::Release);
                    stop_deadline = Instant::now() + Duration::from_secs(2);
                    // Drain at most one second of queued audio, then request final text.
                    while let Ok(chunk) = audio.try_recv() {
                        if Instant::now() >= stop_deadline { break; }
                        if !send(&mut socket, Message::Binary(chunk.into())).await { break; }
                    }
                    let _ = send(&mut socket, Message::Text("{\"type\":\"finish\"}".into())).await;
                    stopping = true;
                }
                incoming = socket.next() => {
                    let Some(Ok(incoming)) = incoming else { break; };
                    if let Message::Text(text) = incoming {
                        let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) else { break; };
                        match value["type"].as_str() {
                            Some("ready") if !stopping => {
                                base_ms = began.elapsed().as_millis() as u64;
                                ready = true; attempts = 0;
                                port.accepting.store(true, Ordering::Release);
                                state(&store, source, "streaming", None, &port);
                            }
                            Some("transcript") if ready => {
                                if let (Some(segment), Some(text), Some(final_text)) = (value["segment"].as_u64(), value["text"].as_str(), value["final"].as_bool()) {
                                    if let Ok(mut store) = store.lock() { store.event(source, epoch, segment, base_ms.saturating_add(segment), text, final_text); }
                                }
                            }
                            Some("error") => {
                                retryable = value["retryable"].as_bool().unwrap_or(false);
                                message = value["message"].as_str().unwrap_or("Transcription unavailable.").chars().take(400).collect();
                                break;
                            }
                            Some("done") => break,
                            _ => {}
                        }
                    } else if incoming.is_close() { break; }
                }
                chunk = audio.recv(), if ready && !stopping => {
                    let Some(chunk) = chunk else { break; };
                    if !send(&mut socket, Message::Binary(chunk.into())).await { break; }
                    last_audio = Instant::now();
                }
                _ = tick.tick() => {
                    if stopping {
                        if Instant::now() >= stop_deadline { break; }
                    } else if port.gap.swap(false, Ordering::AcqRel) {
                        message = "Audio streaming fell behind. Reconnecting; some speech was dropped.".into(); break;
                    } else if !ready && connected_at.elapsed() > Duration::from_secs(10) {
                        break;
                    } else if ready && last_audio.elapsed() > Duration::from_millis(100) {
                        // WASAPI loopback may deliver no packets during silence. Feed
                        // realtime silence so provider endpointing and timestamps advance.
                        if !send(&mut socket, Message::Binary(vec![0u8; 640].into())).await { break; }
                    }
                }
            }
        }
        port.accepting.store(false, Ordering::Release);
        let _ = tokio::time::timeout(Duration::from_millis(500), socket.close(None)).await;
        if *stop.borrow() || stopping {
            break;
        }
        state(
            &store,
            source,
            if retryable { "reconnecting" } else { "error" },
            Some(&message),
            &port,
        );
        if !retryable {
            return;
        }
        attempts += 1;
        if wait_retry(&mut stop, attempts).await {
            break;
        }
    }
    port.accepting.store(false, Ordering::Release);
    state(&store, source, "stopped", None, &port);
}
async fn wait_retry(stop: &mut watch::Receiver<bool>, attempt: u32) -> bool {
    tokio::select! { _ = stop.changed() => true, _ = tokio::time::sleep(Duration::from_millis((500 * (1u64 << attempt.min(5))).min(15000))) => false }
}
async fn send<S>(socket: &mut S, message: Message) -> bool
where
    S: futures_util::Sink<Message> + Unpin,
{
    matches!(
        tokio::time::timeout(Duration::from_millis(500), socket.send(message)).await,
        Ok(Ok(()))
    )
}
