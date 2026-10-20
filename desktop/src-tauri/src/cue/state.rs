use super::transport::{CueInput, CueReply};
use serde::Serialize;
use std::sync::Mutex;
use tokio::sync::watch;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CueCard {
    pub id: u64,
    pub question: String,
    pub status: &'static str,
    pub answer: Option<String>,
    pub grounding: Option<String>,
    pub source_count: usize,
    pub error: Option<String>,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CueSnapshot {
    pub session_id: u64,
    pub cards: Vec<CueCard>,
    pub notice: Option<String>,
}
struct Entry {
    card: CueCard,
    input: CueInput,
    version: u64,
}
struct State {
    active: Option<u64>,
    epoch: u64,
    next: u64,
    entries: Vec<Entry>,
    notice: Option<String>,
}
pub struct Job {
    pub id: u64,
    version: u64,
    pub input: CueInput,
}
pub struct CueService {
    state: Mutex<State>,
    pub gate: tokio::sync::Mutex<()>,
    changed: watch::Sender<u64>,
}
impl Default for CueService {
    fn default() -> Self {
        Self {
            state: Mutex::new(State {
                active: None,
                epoch: 0,
                next: 0,
                entries: vec![],
                notice: None,
            }),
            gate: tokio::sync::Mutex::new(()),
            changed: watch::channel(0).0,
        }
    }
}
impl CueService {
    pub fn reset(&self, active: Option<u64>) {
        if let Ok(mut s) = self.state.lock() {
            s.epoch += 1;
            s.active = active;
            s.entries.clear();
            s.next = 0;
            s.notice = None;
            self.changed.send_replace(s.epoch);
        }
    }
    pub fn lifecycle(&self) -> (u64, watch::Receiver<u64>) {
        let s = self.state.lock().expect("cue state");
        (s.epoch, self.changed.subscribe())
    }
    pub fn active(&self, epoch: u64) -> bool {
        self.state
            .lock()
            .is_ok_and(|s| s.epoch == epoch && s.active.is_some())
    }
    pub fn snapshot(&self) -> Result<CueSnapshot, &'static str> {
        self.state
            .lock()
            .map(|s| CueSnapshot {
                session_id: s.active.unwrap_or(0),
                cards: s.entries.iter().map(|e| e.card.clone()).collect(),
                notice: s.notice.clone(),
            })
            .map_err(|_| "Live Cues are unavailable.")
    }
    pub fn notice(&self, epoch: u64, notice: Option<&str>) {
        if let Ok(mut s) = self.state.lock() {
            if s.epoch == epoch {
                s.notice = notice.map(str::to_owned);
            }
        }
    }
    pub fn enqueue(&self, epoch: u64, target: Option<u64>, input: CueInput) -> Option<u64> {
        let mut s = self.state.lock().ok()?;
        if s.epoch != epoch || s.active.is_none() {
            return None;
        }
        if let Some(id) = target {
            // Removed cards stay removed; conversation state belongs elsewhere.
            if let Some(entry) = s.entries.iter_mut().find(|e| e.card.id == id) {
                if entry.card.question != input.question {
                    entry.version += 1;
                    entry.card.question = input.question.clone();
                    entry.input = input;
                    entry.card.error = None;
                    if entry.card.status != "generating" {
                        entry.card.status = "queued";
                    }
                }
            }
            return Some(id);
        }
        s.next += 1;
        let id = s.next;
        s.entries.push(Entry {
            card: CueCard {
                id,
                question: input.question.clone(),
                status: "queued",
                answer: None,
                grounding: None,
                source_count: 0,
                error: None,
            },
            input,
            version: 1,
        });
        Some(id)
    }
    pub fn next(&self, epoch: u64) -> Option<Job> {
        let mut s = self.state.lock().ok()?;
        if s.epoch != epoch
            || s.active.is_none()
            || s.entries.iter().any(|e| e.card.status == "generating")
        {
            return None;
        }
        let e = s.entries.iter_mut().find(|e| e.card.status == "queued")?;
        e.card.status = "generating";
        Some(Job {
            id: e.card.id,
            version: e.version,
            input: e.input.clone(),
        })
    }
    pub fn finish(&self, epoch: u64, job: Job, result: Result<CueReply, &'static str>) {
        if let Ok(mut s) = self.state.lock() {
            if s.epoch != epoch || s.active.is_none() {
                return;
            }
            let Some(e) = s.entries.iter_mut().find(|e| e.card.id == job.id) else {
                return;
            };
            if e.version != job.version {
                e.card.status = "queued";
                return;
            }
            match result {
                Ok(reply) => {
                    e.card.status = "ready";
                    e.card.answer = Some(reply.answer);
                    e.card.grounding = Some(reply.grounding);
                    e.card.source_count = reply.sources.len();
                    e.input.context.clear();
                }
                Err(message) => {
                    e.card.status = "failed";
                    e.card.error = Some(message.into());
                }
            }
        }
    }
    pub fn remove(&self, session: u64, id: u64) -> Result<(), &'static str> {
        let mut s = self
            .state
            .lock()
            .map_err(|_| "Live Cues are unavailable.")?;
        if s.active == Some(session) {
            s.entries
                .retain(|e| e.card.id != id || e.card.answer.is_none());
        }
        Ok(())
    }
    pub fn retry(&self, session: u64, id: u64) -> Result<(), &'static str> {
        let mut s = self
            .state
            .lock()
            .map_err(|_| "Live Cues are unavailable.")?;
        if s.active == Some(session) {
            if let Some(e) = s
                .entries
                .iter_mut()
                .find(|e| e.card.id == id && e.card.status == "failed")
            {
                e.card.status = "queued";
                e.card.error = None;
            }
        }
        Ok(())
    }
}
