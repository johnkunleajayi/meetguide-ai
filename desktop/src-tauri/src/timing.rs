use serde::Serialize;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub fn unix_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}
pub fn id() -> String {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    format!(
        "q-{:x}-{:x}",
        unix_ms(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    )
}
pub fn emit(value: serde_json::Value) {
    #[cfg(debug_assertions)]
    eprintln!("[MeetGuide Timing] {}", value);
    #[cfg(not(debug_assertions))]
    let _ = value;
}
#[derive(Clone)]
pub struct CandidateTiming {
    pub question_id: String,
    pub final_at: Instant,
    pub candidate_at: Instant,
    pub assembly_wait_ms: f64,
    pub local_detection_ms: f64,
}
impl Default for CandidateTiming {
    fn default() -> Self {
        Self {
            question_id: id(),
            final_at: Instant::now(),
            candidate_at: Instant::now(),
            assembly_wait_ms: 0.0,
            local_detection_ms: 0.0,
        }
    }
}
#[derive(Clone)]
pub struct QuestionTiming {
    pub candidate: CandidateTiming,
    pub detected_at: Instant,
    pub enqueued_at: Instant,
    pub processing_at: Option<Instant>,
    pub intent_route: &'static str,
    pub intent_used: bool,
    pub intent_request_ms: f64,
    pub attempt: u64,
    pub index: u64,
    pub session_age_seconds: f64,
}
impl Default for QuestionTiming {
    fn default() -> Self {
        Self {
            candidate: CandidateTiming::default(),
            detected_at: Instant::now(),
            enqueued_at: Instant::now(),
            processing_at: None,
            intent_route: "local",
            intent_used: false,
            intent_request_ms: 0.0,
            attempt: 0,
            index: 0,
            session_age_seconds: 0.0,
        }
    }
}
impl QuestionTiming {
    pub fn record(&self, stage: &str) -> serde_json::Value {
        serde_json::json!({
            "stage": stage, "question_id": self.candidate.question_id,
            "at_unix_ms": unix_ms(), "session_question_index": self.index,
            "session_age_seconds": self.session_age_seconds, "attempt": self.attempt,
            "intent_route": self.intent_route, "intent_used": self.intent_used,
            "intent_request_ms": self.intent_request_ms,
            "assembly_wait_ms": self.candidate.assembly_wait_ms,
            "local_detection_ms": self.candidate.local_detection_ms,
            "candidate_to_actionable_ms": self.detected_at.saturating_duration_since(self.candidate.candidate_at).as_secs_f64() * 1000.0,
            "native_final_to_question_detected_ms": self.detected_at.saturating_duration_since(self.candidate.final_at).as_secs_f64() * 1000.0,
            "queue_enqueued_at_unix_ms": unix_ms().saturating_sub(self.enqueued_at.elapsed().as_millis()),
            "queue_processing_started_at_unix_ms": self.processing_at.map(|at| unix_ms().saturating_sub(at.elapsed().as_millis())),
            "question_detected_at_unix_ms": unix_ms().saturating_sub(self.detected_at.elapsed().as_millis()),
            "native_final_received_at_unix_ms": unix_ms().saturating_sub(self.candidate.final_at.elapsed().as_millis()),
            "question_detected_to_completion_ms": self.detected_at.elapsed().as_secs_f64() * 1000.0,
            "queue_wait_ms": self.processing_at.map(|at| at.saturating_duration_since(self.enqueued_at).as_secs_f64() * 1000.0),
            "question_detected_to_ready_ms": if stage == "cue_ready" { Some(self.detected_at.elapsed().as_secs_f64() * 1000.0) } else { None },
            "final_transcript_to_ready_ms": if stage == "cue_ready" { Some(self.candidate.final_at.elapsed().as_secs_f64() * 1000.0) } else { None },
        })
    }
}
#[derive(Clone, Default, Serialize)]
pub struct TransportTiming {
    pub backend_processing_ms: Option<f64>,
    pub desktop_request_ms: f64,
    pub desktop_transport_and_processing_ms: Option<f64>,
    pub backend_response_received_at_unix_ms: u128,
}
