//! Conversation candidates, semantic routing and answer execution are independent
//! of the UI and the bounded transcript/event display rings.
use super::{
    intent::{IntentInput, IntentResult},
    state::CueService,
    transport::CueInput,
};
use crate::understanding::{
    candidate::{fingerprint, keys, local_question, Candidate},
    domain::*,
};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

struct Turn {
    id: u64,
    text: String,
    card: Option<u64>,
    question: Option<String>,
}
#[derive(Default)]
pub(super) struct Router {
    turns: VecDeque<Turn>,
    seen: VecDeque<(String, Instant, Option<u64>)>,
    calls: VecDeque<Instant>,
}
fn payload(text: String, context: Vec<ConversationTurn>) -> Option<CueInput> {
    super::input(&MeaningfulEvent {
        id: 0,
        event_type: EventType::Question,
        speaker: Speaker::Them,
        text,
        confidence: 0.9,
        turn_id: 0,
        detected_at_ms: 0,
        context,
    })
}
impl Router {
    pub async fn process<F, Fut>(
        &mut self,
        c: Candidate,
        service: &CueService,
        epoch: u64,
        classify: F,
    ) where
        F: FnOnce(IntentInput) -> Fut,
        Fut: std::future::Future<Output = Result<IntentResult, &'static str>>,
    {
        let now = Instant::now();
        self.seen
            .retain(|(_, at, _)| now.duration_since(*at) < Duration::from_secs(45));
        let short = c.text.split_whitespace().count() <= 5;
        let anchor = if short {
            c.context
                .iter()
                .rev()
                .find(|t| t.speaker == Speaker::You)
                .map(|t| t.id)
                .unwrap_or(0)
        } else {
            0
        };
        // An identical follow-up about a different coding problem is not a replay.
        let code_anchor = if crate::coding::classify(&c.text, service.has_coding_context(epoch))
            == Some(crate::coding::Request::FollowUp)
        {
            service
                .coding_problem(epoch)
                .map(|p| fingerprint(&p))
                .unwrap_or_default()
        } else {
            String::new()
        };
        let key = format!("{}:{anchor}:{code_anchor}", fingerprint(&c.text));
        if let Some((_, _, card)) = self.seen.iter().find(|(seen, _, _)| *seen == key) {
            let card = *card;
            crate::timing::emit(
                serde_json::json!({"stage":"candidate_routing","candidate_id":c.timing.question_id,"local_present":c.local.is_some(),"semantic_attempted":false,"semantic_provider":null,"semantic_outcome":"not_attempted","disposition":"duplicate-suppressed","queue_entry_created":false}),
            );
            self.remember_turn(c.turn_id, c.text, card, None);
            return;
        }
        let previous = self.turns.iter().find(|turn| turn.id == c.turn_id);
        let delta = previous
            .and_then(|p| c.text.strip_prefix(&p.text))
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .unwrap_or(&c.text)
            .to_owned();
        let previous_card = previous.and_then(|p| p.card);
        let previous_request = previous.and_then(|p| p.question.clone());
        let coding = crate::coding::classify(&delta, service.has_coding_context(epoch));
        let local_delta = if coding.is_some() {
            Some(delta.clone())
        } else {
            local_question(&delta, &c.context)
        };
        let linked = delta.split_whitespace().next().is_some_and(|word| {
            matches!(
                word.to_lowercase().as_str(),
                "and" | "but" | "also" | "especially" | "or" | "for" | "with" | "including"
            )
        });
        // A standalone new question is never allowed to overwrite the preceding
        // logical request merely because assembly kept both in one spoken turn.
        let continuation = coding != Some(crate::coding::Request::FollowUp)
            && previous_card.is_some()
            && previous_request.is_some()
            && (linked || local_delta.is_none());
        let local = if coding.is_some() || (previous_card.is_some() && local_delta.is_some()) {
            local_delta.clone()
        } else {
            c.local.clone()
        };
        let tokens = fingerprint(&delta);
        let references = tokens
            .split_whitespace()
            .any(|word| matches!(word, "it" | "that" | "next" | "result"));
        // Length and ASR revision do not make a confident request ambiguous.
        // Keep semantic help for continuations and context-dependent follow-ups.
        let independent = local_question(&delta, &[]).is_some();
        let semantic = coding.is_none()
            && (local.is_none() || continuation || linked || references || !independent);
        // Re-evaluate settled request structure only when semantic assistance is
        // unavailable. This is not a general meaningful-speech-to-question bypass.
        let fallback_question = local
            .clone()
            .or_else(|| local_question(&c.text, &c.context));
        let fallback = || {
            fallback_question.clone().map(|question| IntentResult {
                kind: if continuation && linked {
                    "CONTINUATION"
                } else {
                    "ACTIONABLE_REQUEST"
                }
                .into(),
                normalized_request: if continuation && linked {
                    c.local.clone().unwrap_or(question)
                } else {
                    question
                },
                confidence: 0.9,
            })
        };
        let mut question_timing = crate::timing::QuestionTiming {
            candidate: c.timing.clone(),
            ..Default::default()
        };
        if let Some(id) = previous_card.and_then(|id| service.question_id(epoch, id)) {
            if continuation {
                question_timing.candidate.question_id = id;
            }
        }
        crate::timing::emit(
            serde_json::json!({"stage":"intent_routing","question_id":question_timing.candidate.question_id,"candidate_id":c.timing.question_id,"at_unix_ms":crate::timing::unix_ms()}),
        );
        let intent_started = Instant::now();
        let mut semantic_outcome = "not_attempted";
        let mut degraded = false;
        let result = if semantic {
            self.calls
                .retain(|at| now.duration_since(*at) < Duration::from_secs(60));
            let classification = if self.calls.len() >= 12 {
                Err("Intent budget")
            } else {
                self.calls.push_back(now);
                let input = payload(delta.clone(), c.context.clone());
                if let Some(input) = input {
                    question_timing.intent_used = true;
                    question_timing.intent_route = "openai";
                    classify(IntentInput {
                        question_id: question_timing.candidate.question_id.clone(),
                        text: if previous_card.is_some() {
                            delta
                        } else {
                            c.text.clone()
                        },
                        context: input.context,
                        previous_request: if continuation { previous_request } else { None },
                        can_continue: continuation,
                    })
                    .await
                } else {
                    Err("Invalid intent input")
                }
            };
            match classification {
                Ok(result)
                    if (result.kind != "CONTINUATION" || continuation)
                        && result.confidence >= 0.82 =>
                {
                    semantic_outcome = match result.kind.as_str() {
                        "NOT_ACTIONABLE" => "not_actionable",
                        "CONTINUATION" => "continuation",
                        "FOLLOW_UP" => "follow_up",
                        _ => "actionable",
                    };
                    service.notice(epoch, None);
                    Some(result)
                }
                failure => {
                    semantic_outcome = match failure {
                        Err("Intent budget") => "budget_limited",
                        Err("Intent rate limited") => "rate_limited",
                        Err("Intent timeout") => "timeout",
                        Err("Invalid intent input") => "invalid_input",
                        Err(_) => "unavailable",
                        Ok(ref result) if result.confidence < 0.82 => "low_confidence",
                        Ok(_) => "ineligible_continuation",
                    };
                    degraded = true;
                    question_timing.intent_route = "fallback";
                    service.notice(epoch, Some("Semantic understanding is unavailable. Local question detection remains active."));
                    fallback()
                }
            }
        } else {
            fallback()
        };
        question_timing.intent_request_ms = if question_timing.intent_used {
            intent_started.elapsed().as_secs_f64() * 1000.0
        } else {
            0.0
        };
        question_timing.detected_at = Instant::now();
        let mut card = previous_card;
        let mut question = None;
        let mut enqueued = false;
        if let Some(mut result) = result {
            // Clear grammatical extensions of an existing assembled request
            // remain one logical item even if the provider calls them actionable.
            if continuation
                && linked
                && local_delta.is_none()
                && c.local.is_some()
                && result.kind != "NOT_ACTIONABLE"
            {
                result.kind = "CONTINUATION".into();
                result.normalized_request = c.local.clone().expect("local assembled request");
            }
            if result.kind != "NOT_ACTIONABLE" && result.confidence >= 0.82 {
                question = Some(result.normalized_request.clone());
                if let Some(input) = payload(result.normalized_request, c.context.clone()) {
                    card = service.enqueue_timed(
                        epoch,
                        if result.kind == "CONTINUATION" {
                            previous_card
                        } else {
                            None
                        },
                        input,
                        question_timing.clone(),
                    );
                    enqueued = card.is_some();
                }
            }
        }
        crate::timing::emit(serde_json::json!({
            "stage":"candidate_routing", "candidate_id":c.timing.question_id,
            "question_id":question_timing.candidate.question_id,
            "local_present":local.is_some(), "strong_local_evidence":fallback_question.is_some(), "turn_id":c.turn_id, "revision":c.revision, "semantic_attempted":question_timing.intent_used,
            "semantic_provider":if question_timing.intent_used { Some("openai") } else { None },
            "semantic_outcome":semantic_outcome,
            "disposition":if enqueued { if degraded { "degraded-fallback" } else { "queued" } } else { "rejected" },
            "queue_entry_created":enqueued && previous_card != card
        }));
        self.remember_turn(c.turn_id, c.text.clone(), card, question);
        // Only successful logical requests earn replay suppression. A transient
        // classification failure must remain eligible for a later replay.
        if !enqueued {
            return;
        }
        for alias in keys(&c.text)
            .into_iter()
            .chain(std::iter::once(fingerprint(&c.text)))
        {
            self.seen
                .push_back((format!("{alias}:{anchor}:{code_anchor}"), now, card));
        }
        while self.seen.len() > 128 {
            self.seen.pop_front();
        }
    }
    fn remember_turn(
        &mut self,
        id: u64,
        text: String,
        card: Option<u64>,
        question: Option<String>,
    ) {
        if let Some(turn) = self.turns.iter_mut().find(|t| t.id == id) {
            turn.text = text;
            turn.card = card;
            if question.is_some() {
                turn.question = question;
            }
        } else {
            self.turns.push_back(Turn {
                id,
                text,
                card,
                question,
            });
        }
        while self.turns.len() > 32 {
            self.turns.pop_front();
        }
    }
}

pub fn start(store: Arc<Mutex<crate::transcription::TranscriptStore>>, service: Arc<CueService>) {
    let (epoch, mut cancelled) = service.lifecycle();
    let answers = service.clone();
    tauri::async_runtime::spawn(async move {
        let mut router = Router::default();
        while service.active(epoch) {
            let candidates = if let Ok(mut store) = store.lock() {
                store.tick_understanding();
                store.take_candidates()
            } else {
                vec![]
            };
            for candidate in candidates {
                tokio::select! {
                    biased;
                    _ = cancelled.changed() => return,
                    _ = router.process(candidate, &service, epoch, super::intent::classify) => {}
                }
            }
            tokio::select! { _ = cancelled.changed() => return, _ = tokio::time::sleep(Duration::from_millis(150)) => {} }
        }
    });
    let (_, mut cancelled) = answers.lifecycle();
    tauri::async_runtime::spawn(async move {
        while answers.active(epoch) {
            let gate = tokio::select! { biased; _ = cancelled.changed() => return, gate = answers.gate.lock() => gate };
            if let Some(job) = answers.next(epoch) {
                let result = tokio::select! { biased; _ = cancelled.changed() => return, result = super::transport::generate(job.input.clone(), &job.timing.candidate.question_id, job.preparation_token.as_deref().map(|s| s.as_str()), job.timing.attempt, |text, code| answers.progress_code(epoch, &job, text, code)) => result };
                answers.finish(epoch, job, result);
            }
            drop(gate);
            tokio::select! { _ = cancelled.changed() => return, _ = tokio::time::sleep(Duration::from_millis(100)) => {} }
        }
    });
}
