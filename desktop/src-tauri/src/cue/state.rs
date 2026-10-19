use serde::Serialize;
use std::sync::Mutex;
use tokio::sync::watch;

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CueSnapshot {
    pub session_id: u64,
    pub event_id: u64,
    pub status: &'static str,
    pub answer: Option<String>,
    pub grounding: Option<String>,
    pub source_count: usize,
    pub error: Option<String>,
}
struct State {
    active: Option<u64>,
    sequence: u64,
    snapshot: CueSnapshot,
}
pub struct CueService {
    state: Mutex<State>,
    changed: watch::Sender<u64>,
}
impl Default for CueService {
    fn default() -> Self {
        Self {
            state: Mutex::new(State {
                active: None,
                sequence: 0,
                snapshot: CueSnapshot {
                    status: "idle",
                    ..Default::default()
                },
            }),
            changed: watch::channel(0).0,
        }
    }
}
impl CueService {
    pub fn reset(&self, active: Option<u64>) {
        if let Ok(mut state) = self.state.lock() {
            state.sequence += 1;
            state.active = active;
            state.snapshot = CueSnapshot {
                session_id: active.unwrap_or(0),
                status: "idle",
                ..Default::default()
            };
            self.changed.send_replace(state.sequence);
        }
    }
    pub fn snapshot(&self) -> Result<CueSnapshot, &'static str> {
        self.state
            .lock()
            .map(|s| s.snapshot.clone())
            .map_err(|_| "Live Cue is unavailable.")
    }
    pub fn begin(
        &self,
        session: u64,
        event: u64,
        retry: bool,
    ) -> Option<(u64, watch::Receiver<u64>)> {
        let mut state = self.state.lock().ok()?;
        if state.active != Some(session) {
            return None;
        }
        if state.snapshot.event_id == event && (state.snapshot.status != "error" || !retry) {
            return None;
        }
        state.sequence += 1;
        state.snapshot = CueSnapshot {
            session_id: session,
            event_id: event,
            status: "preparing",
            ..Default::default()
        };
        self.changed.send_replace(state.sequence);
        Some((state.sequence, self.changed.subscribe()))
    }
    pub fn finish(&self, sequence: u64, result: Result<super::transport::CueReply, &'static str>) {
        if let Ok(mut state) = self.state.lock() {
            if state.sequence != sequence || state.active.is_none() {
                return;
            }
            match result {
                Ok(reply) => {
                    state.snapshot.status = "ready";
                    state.snapshot.answer = Some(reply.answer);
                    state.snapshot.grounding = Some(reply.grounding);
                    state.snapshot.source_count = reply.sources.len();
                }
                Err(message) => {
                    state.snapshot.status = "error";
                    state.snapshot.error = Some(message.into());
                }
            }
        }
    }
}
