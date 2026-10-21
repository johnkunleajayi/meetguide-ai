use super::transport::{CodeAssist, CodingContext, CueInput, CueReply};
use crate::timing::{emit, unix_ms, QuestionTiming};
use serde::Serialize;
use std::sync::Mutex;
use std::time::Instant;
use tokio::sync::watch;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CueCard {
    pub id: u64,
    pub attempt: u64,
    pub question_id: String,
    pub ready_at_unix_ms: Option<u128>,
    pub first_output_at_unix_ms: Option<u128>,
    pub cue_kind: &'static str,
    pub code_assist: Option<CodeAssist>,
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
    timing: QuestionTiming,
    card: CueCard,
    input: CueInput,
    version: u64,
}
struct State {
    current_code: Option<CodingContext>,
    last_code: Option<CodingContext>,
    in_flight: Option<(u64, u64)>,
    preparation_token: Option<zeroize::Zeroizing<String>>,
    began: Instant,
    active: Option<u64>,
    epoch: u64,
    next: u64,
    entries: Vec<Entry>,
    notice: Option<String>,
}
pub struct Job {
    pub preparation_token: Option<zeroize::Zeroizing<String>>,
    pub timing: QuestionTiming,
    pub id: u64,
    version: u64,
    pub input: CueInput,
}
pub struct CueService {
    publisher: Mutex<Option<std::sync::Arc<dyn Fn(CueSnapshot) + Send + Sync>>>,
    state: Mutex<State>,
    pub gate: tokio::sync::Mutex<()>,
    changed: watch::Sender<u64>,
}
impl Default for CueService {
    fn default() -> Self {
        Self {
            publisher: Mutex::new(None),
            state: Mutex::new(State {
                current_code: None,
                last_code: None,
                in_flight: None,
                preparation_token: None,
                began: Instant::now(),
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
    pub fn set_publisher(&self, publisher: std::sync::Arc<dyn Fn(CueSnapshot) + Send + Sync>) {
        if let Ok(mut handle) = self.publisher.lock() {
            *handle = Some(publisher);
        }
    }
    fn publish(&self, s: &State) {
        if let Ok(handle) = self.publisher.lock() {
            if let Some(publish) = handle.as_ref() {
                publish(CueSnapshot {
                    session_id: s.active.unwrap_or(0),
                    cards: s.entries.iter().map(|e| e.card.clone()).collect(),
                    notice: s.notice.clone(),
                });
            }
        }
    }
    #[cfg(test)]
    pub fn progress(&self, epoch: u64, job: &Job, answer: Option<&str>) {
        self.progress_code(epoch, job, answer, None);
    }
    pub fn progress_code(
        &self,
        epoch: u64,
        job: &Job,
        answer: Option<&str>,
        code: Option<&CodeAssist>,
    ) {
        if let Ok(mut s) = self.state.lock() {
            if s.epoch != epoch || s.active.is_none() {
                return;
            }
            if let Some(e) = s
                .entries
                .iter_mut()
                .find(|e| e.card.id == job.id && e.version == job.version)
            {
                if !matches!(e.card.status, "generating" | "responding") {
                    return;
                }
                if let Some(text) = answer {
                    if text.is_empty() || text.chars().count() > 2400 {
                        return;
                    }
                    if e.card.first_output_at_unix_ms.is_none() {
                        e.card.first_output_at_unix_ms = Some(unix_ms());
                        let mut record = job.timing.record("cue_first_output");
                        record["question_detected_to_first_output_ms"] = serde_json::json!(
                            job.timing.detected_at.elapsed().as_secs_f64() * 1000.0
                        );
                        record["final_transcript_to_first_output_ms"] = serde_json::json!(
                            job.timing.candidate.final_at.elapsed().as_secs_f64() * 1000.0
                        );
                        emit(record);
                    }
                    e.card.status = "responding";
                    e.card.answer = Some(text.into());
                    e.card.code_assist = code.cloned();
                } else {
                    e.card.status = "generating";
                    e.card.answer = None;
                    e.card.code_assist = None;
                }
                self.publish(&s);
            }
        }
    }

    pub fn reset(&self, active: Option<u64>) {
        if let Ok(mut s) = self.state.lock() {
            s.current_code = None;
            s.last_code = None;
            s.in_flight = None;
            s.preparation_token = None;
            s.began = Instant::now();
            s.epoch += 1;
            s.active = active;
            s.entries.clear();
            s.next = 0;
            s.notice = None;
            self.changed.send_replace(s.epoch);
            self.publish(&s);
        }
    }
    pub fn set_preparation(&self, token: Option<zeroize::Zeroizing<String>>) {
        if let Ok(mut s) = self.state.lock() {
            s.preparation_token = token;
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
                self.publish(&s);
            }
        }
    }
    pub fn coding_problem(&self, epoch: u64) -> Option<String> {
        let s = self.state.lock().ok()?;
        if s.epoch != epoch {
            return None;
        }
        s.current_code.as_ref().map(|c| c.problem.clone())
    }
    pub fn has_coding_context(&self, epoch: u64) -> bool {
        self.state
            .lock()
            .is_ok_and(|s| s.epoch == epoch && s.current_code.is_some())
    }
    pub fn question_id(&self, epoch: u64, id: u64) -> Option<String> {
        let s = self.state.lock().ok()?;
        if s.epoch != epoch {
            return None;
        }
        s.entries
            .iter()
            .find(|e| e.card.id == id)
            .map(|e| e.card.question_id.clone())
    }
    #[cfg(test)]
    pub fn enqueue(&self, epoch: u64, target: Option<u64>, input: CueInput) -> Option<u64> {
        self.enqueue_timed(epoch, target, input, QuestionTiming::default())
    }
    pub fn enqueue_timed(
        &self,
        epoch: u64,
        target: Option<u64>,
        mut input: CueInput,
        mut timing: QuestionTiming,
    ) -> Option<u64> {
        let mut s = self.state.lock().ok()?;
        if s.epoch != epoch || s.active.is_none() {
            return None;
        }
        timing.enqueued_at = Instant::now();
        timing.session_age_seconds = s.began.elapsed().as_secs_f64();
        if let Some(id) = target {
            let mut amended_code = None;
            // Removed cards stay removed; conversation state belongs elsewhere.
            if let Some(entry) = s.entries.iter_mut().find(|e| e.card.id == id) {
                if entry.card.question != input.question {
                    timing.index = entry.timing.index;
                    timing.attempt = entry.timing.attempt;
                    timing.candidate.question_id = entry.card.question_id.clone();
                    emit(timing.record("queue_enriched"));
                    entry.timing = timing;
                    entry.version += 1;
                    entry.card.question = input.question.clone();
                    if entry.input.cue_kind == "code" {
                        input.cue_kind = "code";
                        input.coding_context = entry.input.coding_context.clone();
                        if input.coding_context.is_none() {
                            amended_code = Some(CodingContext {
                                problem: input.question.clone(),
                                language: "auto".into(),
                                code: String::new(),
                            });
                        }
                    }
                    entry.input = input;
                    entry.card.error = None;
                    if entry.card.status == "responding" {
                        entry.card.code_assist = None;
                        entry.card.answer = None;
                        entry.card.status = "generating";
                    }
                    if entry.card.status != "generating" {
                        entry.card.status = "queued";
                    }
                }
            }
            if let Some(context) = amended_code {
                s.current_code = Some(context);
            }
            self.publish(&s);
            return Some(id);
        }
        if let Some(kind) = crate::coding::classify(&input.question, s.current_code.is_some()) {
            input.cue_kind = "code";
            if kind == crate::coding::Request::FollowUp {
                input.coding_context = s.current_code.clone();
            }
            s.current_code = Some(input.coding_context.clone().unwrap_or(CodingContext {
                problem: input.question.clone(),
                language: "auto".into(),
                code: String::new(),
            }));
        } else {
            s.current_code = None;
        }
        s.next += 1;
        let id = s.next;
        timing.index = id;
        emit(timing.record("queue_enqueued"));
        s.entries.push(Entry {
            timing: timing.clone(),
            card: CueCard {
                id,
                attempt: 0,
                question_id: timing.candidate.question_id.clone(),
                ready_at_unix_ms: None,
                first_output_at_unix_ms: None,
                cue_kind: input.cue_kind,
                code_assist: None,
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
        self.publish(&s);
        Some(id)
    }
    pub fn next(&self, epoch: u64) -> Option<Job> {
        let mut s = self.state.lock().ok()?;
        if s.epoch != epoch || s.active.is_none() || s.in_flight.is_some() {
            return None;
        }
        let preparation_token = s.preparation_token.clone();
        let last_code = s.last_code.clone();
        let e = s.entries.iter_mut().find(|e| e.card.status == "queued")?;
        if e.card.attempt == 0 {
            if let (Some(context), Some(previous)) = (&mut e.input.coding_context, &last_code) {
                if context.problem == previous.problem {
                    *context = previous.clone();
                }
            }
        }
        e.timing.processing_at = Some(Instant::now());
        e.timing.attempt += 1;
        e.card.attempt = e.timing.attempt;
        emit(e.timing.record("queue_processing_started"));
        e.card.status = "generating";
        e.card.answer = None;
        e.card.code_assist = None;
        e.card.first_output_at_unix_ms = None;
        let job = Job {
            preparation_token,
            timing: e.timing.clone(),
            id: e.card.id,
            version: e.version,
            input: e.input.clone(),
        };
        s.in_flight = Some((job.id, job.version));
        self.publish(&s);
        Some(job)
    }
    pub fn finish(&self, epoch: u64, job: Job, result: Result<CueReply, &'static str>) {
        if let Ok(mut s) = self.state.lock() {
            if s.epoch != epoch || s.active.is_none() {
                return;
            }
            if s.in_flight == Some((job.id, job.version)) {
                s.in_flight = None;
            }
            let valid = s
                .entries
                .iter()
                .find(|e| e.card.id == job.id)
                .is_none_or(|e| e.version == job.version);
            if valid {
                if let Ok(reply) = &result {
                    if let Some(code) = &reply.code_assist {
                        let context = CodingContext {
                            problem: job
                                .input
                                .coding_context
                                .as_ref()
                                .map(|c| c.problem.clone())
                                .unwrap_or_else(|| job.input.question.clone()),
                            language: code.language.clone(),
                            code: code.code.clone(),
                        };
                        if s.current_code
                            .as_ref()
                            .is_some_and(|c| c.problem == context.problem)
                        {
                            s.current_code = Some(context.clone());
                        }
                        s.last_code = Some(context);
                    }
                }
            }
            let Some(e) = s.entries.iter_mut().find(|e| e.card.id == job.id) else {
                return;
            };
            if e.version != job.version {
                emit(job.timing.record("cue_superseded"));
                e.card.status = "queued";
                e.card.answer = None;
                e.card.code_assist = None;
                self.publish(&s);
                return;
            }
            match result {
                Ok(reply) => {
                    let mut record = job.timing.record("cue_ready");
                    record["transport"] = serde_json::to_value(&reply.timing).unwrap_or_default();
                    emit(record);
                    e.card.ready_at_unix_ms = Some(unix_ms());
                    e.card.status = "ready";
                    e.card.answer = Some(reply.answer);
                    e.card.code_assist = reply.code_assist;
                    e.card.grounding = Some(reply.grounding);
                    e.card.source_count = reply.sources.len();
                    e.input.context.clear();
                }
                Err(message) => {
                    emit(job.timing.record("cue_failed"));
                    e.card.answer = None;
                    e.card.code_assist = None;
                    e.card.grounding = None;
                    e.card.status = "failed";
                    e.card.error = Some(message.into());
                }
            }
            self.publish(&s);
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
            self.publish(&s);
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
                e.timing.enqueued_at = Instant::now();
                e.timing.processing_at = None;
                emit(e.timing.record("retry_enqueued"));
                e.card.status = "queued";
                e.card.error = None;
                e.card.answer = None;
                e.card.first_output_at_unix_ms = None;
                self.publish(&s);
            }
        }
        Ok(())
    }
}
