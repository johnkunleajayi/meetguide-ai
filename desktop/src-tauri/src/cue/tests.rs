use super::*;
use crate::understanding::{candidate::Candidate, domain::ConversationTurn, UnderstandingEngine};
fn request(question: &str) -> CueInput {
    CueInput {
        cue_kind: "conversation",
        coding_context: None,
        event_type: "question",
        speaker: "them",
        finalized: true,
        confidence: 0.94,
        question: question.into(),
        context: vec![],
    }
}
fn reply() -> transport::CueReply {
    transport::CueReply {
        timing: Default::default(),
        code_assist: None,
        answer: "I tested the integration.\n\nI checked the result.".into(),
        grounding: "general_approach".into(),
        sources: vec![],
    }
}
fn service() -> (CueService, u64) {
    let s = CueService::default();
    s.reset(Some(1));
    let epoch = s.lifecycle().0;
    (s, epoch)
}
fn candidate(id: u64, text: &str, local: Option<&str>, revision: u64) -> Candidate {
    Candidate {
        timing: Default::default(),
        turn_id: id,
        revision,
        text: text.into(),
        context: vec![],
        local: local.map(str::to_owned),
    }
}
async fn unavailable(_: intent::IntentInput) -> Result<intent::IntentResult, &'static str> {
    Err("mock unavailable")
}
async fn action(input: intent::IntentInput) -> Result<intent::IntentResult, &'static str> {
    Ok(intent::IntentResult {
        kind: "ACTIONABLE_REQUEST".into(),
        normalized_request: input.text,
        confidence: 0.94,
    })
}
#[test]
fn fifo_preserves_three_questions_and_one_generating_request() {
    let (s, epoch) = service();
    s.enqueue(epoch, None, request("Question one?"));
    let one = s.next(epoch).unwrap();
    s.enqueue(epoch, None, request("Question two?"));
    s.enqueue(epoch, None, request("Question three?"));
    assert!(s.next(epoch).is_none());
    s.finish(epoch, one, Ok(reply()));
    for expected in [2, 3] {
        let job = s.next(epoch).unwrap();
        assert_eq!(job.id, expected);
        s.finish(epoch, job, Ok(reply()));
    }
    let snapshot = s.snapshot().unwrap();
    assert_eq!(snapshot.cards.len(), 3);
    assert!(snapshot.cards.iter().all(|c| c.status == "ready"));
}
#[test]
fn remove_middle_card_preserves_queue_context_and_accepts_q4() {
    let audio = crate::audio::AudioService::default();
    audio
        .transcript
        .lock()
        .unwrap()
        .reset(&[crate::transcription::Source::System]);
    audio.cues.reset(Some(1));
    let epoch = audio.cues.lifecycle().0;
    for question in ["Question one?", "Question two?", "Question three?"] {
        audio.cues.enqueue(epoch, None, request(question));
        let job = audio.cues.next(epoch).unwrap();
        audio.cues.finish(epoch, job, Ok(reply()));
    }
    let before = serde_json::to_value(&audio.transcript.lock().unwrap().snapshot).unwrap();
    audio.cues.remove(1, 2).unwrap();
    assert_eq!(
        audio
            .cues
            .snapshot()
            .unwrap()
            .cards
            .iter()
            .map(|c| c.id)
            .collect::<Vec<_>>(),
        vec![1, 3]
    );
    assert_eq!(
        before,
        serde_json::to_value(&audio.transcript.lock().unwrap().snapshot).unwrap()
    );
    assert!(
        audio
            .transcript
            .lock()
            .unwrap()
            .snapshot
            .understanding
            .active
    );
    audio.cues.enqueue(epoch, None, request("Question four?"));
    let job = audio.cues.next(epoch).unwrap();
    assert_eq!(job.id, 4);
    audio.cues.finish(epoch, job, Ok(reply()));
    assert_eq!(audio.cues.snapshot().unwrap().cards.len(), 3);
}
#[test]
fn completed_cards_have_no_count_pruning_and_reset_invalidates_late_results() {
    let (s, epoch) = service();
    for id in 0..40 {
        s.enqueue(epoch, None, request(&format!("Question {id}?")));
        let job = s.next(epoch).unwrap();
        s.finish(epoch, job, Ok(reply()));
    }
    assert_eq!(s.snapshot().unwrap().cards.len(), 40);
    s.enqueue(epoch, None, request("Pending question?"));
    let old = s.next(epoch).unwrap();
    s.reset(None);
    s.finish(epoch, old, Ok(reply()));
    assert!(s.snapshot().unwrap().cards.is_empty());
    assert!(s.next(epoch).is_none());
    s.reset(Some(2));
    assert!(s.snapshot().unwrap().cards.is_empty());
}
#[test]
fn continuation_enriches_one_card_and_rejects_obsolete_answer() {
    let (s, epoch) = service();
    let id = s
        .enqueue(epoch, None, request("Tell me about the integration."))
        .unwrap();
    let old = s.next(epoch).unwrap();
    s.enqueue(
        epoch,
        Some(id),
        request("Tell me about the integration and challenges."),
    );
    s.finish(epoch, old, Ok(reply()));
    assert_eq!(s.snapshot().unwrap().cards[0].status, "queued");
    let new = s.next(epoch).unwrap();
    s.finish(epoch, new, Ok(reply()));
    assert_eq!(s.snapshot().unwrap().cards.len(), 1);
    s.remove(1, id).unwrap();
    s.enqueue(epoch, Some(id), request("A further qualifier."));
    assert!(s.snapshot().unwrap().cards.is_empty());
}
#[test]
fn failed_question_does_not_block_next_and_can_retry() {
    let (s, epoch) = service();
    s.enqueue(epoch, None, request("First?"));
    s.enqueue(epoch, None, request("Second?"));
    let one = s.next(epoch).unwrap();
    s.finish(epoch, one, Err("Mock failure"));
    let two = s.next(epoch).unwrap();
    s.finish(epoch, two, Ok(reply()));
    s.retry(1, 1).unwrap();
    let retry = s.next(epoch).unwrap();
    s.finish(epoch, retry, Ok(reply()));
    assert!(s
        .snapshot()
        .unwrap()
        .cards
        .iter()
        .all(|c| c.status == "ready"));
}
#[tokio::test(flavor = "current_thread")]
async fn exact_two_question_regression_produces_two_retained_cards_without_clear() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    for (id, text, now) in [
        (
            1,
            "Tell me about a Salesforce integration you worked on.",
            0,
        ),
        (2, "And challenges you faced.", 600),
    ] {
        e.finalized(Speaker::Them, 1, id, text, now, now);
    }
    assert!(e.tick(1800));
    for c in e.take_candidates() {
        router.process(c, &s, epoch, action).await;
    }
    let one = s.next(epoch).unwrap();
    s.finish(epoch, one, Ok(reply()));
    for (id, text, now) in [
        (3, "How did you undo", 8000),
        (4, "the Salesforce migration?", 8600),
    ] {
        e.finalized(Speaker::Them, 1, id, text, now, now);
    }
    assert!(e.tick(9800));
    for c in e.take_candidates() {
        router.process(c, &s, epoch, action).await;
    }
    let two = s.next(epoch).unwrap();
    s.finish(epoch, two, Ok(reply()));
    let cards = s.snapshot().unwrap().cards;
    assert_eq!(cards.len(), 2);
    assert!(cards[1].question.contains("undo the Salesforce migration"));
    assert!(cards.iter().all(|c| c.status == "ready"));
}
#[tokio::test(flavor = "current_thread")]
async fn semantic_continuation_updates_one_question_and_duplicates_do_not_call_provider() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    router
        .process(
            candidate(
                1,
                "Tell me about the integration.",
                Some("Tell me about the integration."),
                1,
            ),
            &s,
            epoch,
            unavailable,
        )
        .await;
    router
        .process(
            candidate(
                1,
                "Tell me about the integration. And challenges you faced.",
                Some("Tell me about the integration and challenges you faced."),
                2,
            ),
            &s,
            epoch,
            |input| async move {
                assert!(input.can_continue);
                assert!(input.previous_request.is_some());
                Ok(intent::IntentResult {
                    kind: "CONTINUATION".into(),
                    normalized_request: "Tell me about the integration and challenges you faced."
                        .into(),
                    confidence: 0.95,
                })
            },
        )
        .await;
    assert_eq!(s.snapshot().unwrap().cards.len(), 1);
    router
        .process(
            candidate(
                2,
                "Tell me about the integration. And challenges you faced.",
                None,
                2,
            ),
            &s,
            epoch,
            |_| async { panic!("duplicate must not call Gemini") },
        )
        .await;
    assert_eq!(s.snapshot().unwrap().cards.len(), 1);
}
#[tokio::test(flavor = "current_thread")]
async fn uncertain_speech_reaches_intent_and_unavailable_falls_back() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    router
        .process(
            candidate(1, "I'd like to hear more about your approach.", None, 1),
            &s,
            epoch,
            action,
        )
        .await;
    router
        .process(
            candidate(
                2,
                "How did you test that?",
                Some("How did you test that?"),
                2,
            ),
            &s,
            epoch,
            unavailable,
        )
        .await;
    assert_eq!(s.snapshot().unwrap().cards.len(), 2);
    assert!(s.snapshot().unwrap().notice.is_some());
    router
        .process(
            candidate(3, "We completed the migration successfully.", None, 1),
            &s,
            epoch,
            |_| async {
                Ok(intent::IntentResult {
                    kind: "NOT_ACTIONABLE".into(),
                    normalized_request: "".into(),
                    confidence: 0.95,
                })
            },
        )
        .await;
    assert_eq!(s.snapshot().unwrap().cards.len(), 2);
}
#[test]
fn local_gate_ignores_you_acknowledgements_and_duplicate_finals() {
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    e.finalized(
        Speaker::You,
        1,
        1,
        "Tell me about your professional integration experience.",
        0,
        0,
    );
    e.tick(1200);
    assert!(e.take_candidates().is_empty());
    for (id, text) in [(2, "okay"), (3, "right"), (4, "I see"), (5, "interesting")] {
        e.finalized(Speaker::Them, 1, id, text, id * 4000, id * 4000);
        e.tick(id * 4000 + 1200);
        assert!(e.take_candidates().is_empty());
    }
    e.finalized(
        Speaker::Them,
        1,
        6,
        "Tell me about your professional integration experience.",
        30000,
        30000,
    );
    e.tick(31200);
    assert_eq!(e.take_candidates().len(), 1);
    e.finalized(
        Speaker::Them,
        1,
        6,
        "Tell me about your professional integration experience.",
        31000,
        31000,
    );
    e.tick(32200);
    assert!(e.take_candidates().is_empty());
}
#[test]
fn question_inputs_keep_bounded_context_and_source_identity() {
    let context = (0..20)
        .map(|id| ConversationTurn {
            id,
            speaker: Speaker::You,
            text: "x".repeat(3000),
            started_at_ms: id,
            last_segment_at_ms: id,
            epoch: 1,
            revision: 1,
        })
        .collect();
    let event = MeaningfulEvent {
        id: 1,
        event_type: EventType::Question,
        speaker: Speaker::Them,
        text: "How did you test it?".into(),
        confidence: 0.94,
        turn_id: 1,
        detected_at_ms: 0,
        context,
    };
    let request = input(&event).unwrap();
    assert!(request.context.len() <= 6);
    assert!(request.context.iter().map(|t| t.text.len()).sum::<usize>() <= 4000);
}

#[tokio::test(flavor = "current_thread")]
async fn contextual_followup_is_a_distinct_request_and_gets_bounded_transcript_only() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    router
        .process(
            candidate(
                1,
                "Tell me about your integration experience.",
                Some("Tell me about your integration experience."),
                1,
            ),
            &s,
            epoch,
            unavailable,
        )
        .await;
    let mut followup = candidate(2, "Why?", Some("Why?"), 1);
    followup.context = (0..20)
        .map(|id| ConversationTurn {
            id,
            speaker: Speaker::You,
            text: "x".repeat(1000),
            started_at_ms: id,
            last_segment_at_ms: id,
            epoch: 1,
            revision: 1,
        })
        .collect();
    router
        .process(followup, &s, epoch, |input| async move {
            assert!(!input.can_continue);
            assert!(input.previous_request.is_none());
            assert!(input.context.len() <= 6);
            assert!(input.context.iter().map(|t| t.text.len()).sum::<usize>() <= 4000);
            Ok(intent::IntentResult {
                kind: "FOLLOW_UP".into(),
                normalized_request: "Why did you choose that integration approach?".into(),
                confidence: 0.95,
            })
        })
        .await;
    assert_eq!(s.snapshot().unwrap().cards.len(), 2);
}

#[tokio::test(flavor = "current_thread")]
async fn obvious_requests_are_local_and_low_confidence_intent_falls_back() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    router
        .process(
            candidate(
                1,
                "Tell me about your integration experience.",
                Some("Tell me about your integration experience."),
                1,
            ),
            &s,
            epoch,
            |_| async { panic!("obvious question must stay local") },
        )
        .await;
    router
        .process(
            candidate(
                2,
                "How did you test that?",
                Some("How did you test that?"),
                2,
            ),
            &s,
            epoch,
            |_| async {
                Ok(intent::IntentResult {
                    kind: "NOT_ACTIONABLE".into(),
                    normalized_request: "".into(),
                    confidence: 0.2,
                })
            },
        )
        .await;
    assert_eq!(s.snapshot().unwrap().cards.len(), 2);
}

#[tokio::test(flavor = "current_thread")]
async fn three_distinct_quiet_candidates_survive_pending_assembly_and_route_fifo() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    for (id, text, now) in [
        (1, "Tell me about your integration experience.", 0),
        (2, "Tell me about your leadership experience.", 300),
        (3, "Tell me about your project management experience.", 600),
    ] {
        e.finalized(Speaker::Them, 1, id, text, now, now);
    }
    assert!(e.tick(1800));
    let candidates = e.take_candidates();
    assert_eq!(candidates.len(), 3);
    for c in candidates {
        router.process(c, &s, epoch, unavailable).await;
    }
    for id in 1..=3 {
        let job = s.next(epoch).unwrap();
        assert_eq!(job.id, id);
        s.finish(epoch, job, Ok(reply()));
    }
    assert_eq!(s.snapshot().unwrap().cards.len(), 3);
}

#[test]
fn completed_card_stays_readable_while_a_late_continuation_is_prepared() {
    let (s, epoch) = service();
    let id = s
        .enqueue(epoch, None, request("Tell me about the integration."))
        .unwrap();
    let job = s.next(epoch).unwrap();
    s.finish(epoch, job, Ok(reply()));
    let answer = s.snapshot().unwrap().cards[0].answer.clone();
    s.enqueue(
        epoch,
        Some(id),
        request("Tell me about the integration and challenges."),
    );
    assert_eq!(s.snapshot().unwrap().cards[0].answer, answer);
    assert_eq!(s.snapshot().unwrap().cards.len(), 1);
}

#[tokio::test(flavor = "current_thread")]
async fn a_distinct_new_question_cannot_be_overwritten_by_a_wrong_continuation_label() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    router
        .process(
            candidate(
                1,
                "Tell me about your integration experience.",
                Some("Tell me about your integration experience."),
                1,
            ),
            &s,
            epoch,
            unavailable,
        )
        .await;
    router
        .process(
            candidate(
                1,
                "Tell me about your integration experience. How did you handle the migration?",
                Some(
                    "Tell me about your integration experience. How did you handle the migration?",
                ),
                2,
            ),
            &s,
            epoch,
            |input| async move {
                assert!(!input.can_continue);
                assert_eq!(input.text, "How did you handle the migration?");
                Ok(intent::IntentResult {
                    kind: "CONTINUATION".into(),
                    normalized_request: "Wrong replacement".into(),
                    confidence: 0.95,
                })
            },
        )
        .await;
    let cards = s.snapshot().unwrap().cards;
    assert_eq!(cards.len(), 2);
    assert_eq!(cards[1].question, "How did you handle the migration?");
}

#[tokio::test(flavor = "current_thread")]
async fn semantic_budget_limits_calls_but_local_fallback_preserves_known_questions() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    let calls = std::cell::Cell::new(0);
    for id in 1..=13 {
        let text = format!("How did you test that in project {id}?");
        router
            .process(candidate(id, &text, Some(&text), 2), &s, epoch, |input| {
                calls.set(calls.get() + 1);
                async move {
                    Ok(intent::IntentResult {
                        kind: "ACTIONABLE_REQUEST".into(),
                        normalized_request: input.text,
                        confidence: 0.95,
                    })
                }
            })
            .await;
    }
    assert_eq!(calls.get(), 12);
    assert_eq!(s.snapshot().unwrap().cards.len(), 13);
}

#[tokio::test(flavor = "current_thread")]
async fn candidate_outbox_and_cue_feed_are_independent_of_eight_event_display_ring() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    for id in 1..=40 {
        let text = format!("Tell me about your integration project {id}.");
        e.finalized(Speaker::Them, 1, id, &text, id * 5000, id * 5000);
        assert!(e.tick(id * 5000 + 1200));
    }
    assert_eq!(e.snapshot.events.len(), 8);
    let candidates = e.take_candidates();
    assert_eq!(candidates.len(), 40);
    for c in candidates {
        router.process(c, &s, epoch, unavailable).await;
    }
    for _ in 0..40 {
        let job = s.next(epoch).unwrap();
        s.finish(epoch, job, Ok(reply()));
    }
    assert_eq!(s.snapshot().unwrap().cards.len(), 40);
}

#[test]
fn meaningful_local_rejection_is_offered_to_semantic_routing() {
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    e.finalized(
        Speaker::Them,
        1,
        1,
        "I'd like to hear more about your approach.",
        0,
        0,
    );
    assert!(!e.tick(1200));
    let candidates = e.take_candidates();
    assert_eq!(candidates.len(), 1);
    assert!(candidates[0].local.is_none());
}

#[tokio::test(flavor = "current_thread")]
async fn an_actionable_label_for_a_clear_assembled_continuation_does_not_duplicate_cards() {
    let (s, epoch) = service();
    let mut router = worker::Router::default();
    router
        .process(
            candidate(
                1,
                "Tell me about the integration.",
                Some("Tell me about the integration."),
                1,
            ),
            &s,
            epoch,
            unavailable,
        )
        .await;
    router
        .process(
            candidate(
                1,
                "Tell me about the integration. And challenges you faced.",
                Some("Tell me about the integration and challenges you faced."),
                2,
            ),
            &s,
            epoch,
            action,
        )
        .await;
    let cards = s.snapshot().unwrap().cards;
    assert_eq!(cards.len(), 1);
    assert!(cards[0].question.contains("integration and challenges"));
}

#[test]
fn timing_preserves_queue_ids_counts_failure_and_retry() {
    let (s, epoch) = service();
    let first = s
        .enqueue(epoch, None, request("How did you handle the integration?"))
        .unwrap();
    let second = s
        .enqueue(epoch, None, request("What was the result?"))
        .unwrap();
    std::thread::sleep(std::time::Duration::from_millis(3));
    let job = s.next(epoch).unwrap();
    assert!(
        job.timing.record("queue_processing_started")["queue_wait_ms"]
            .as_f64()
            .unwrap()
            >= 3.0
    );
    assert!(job.timing.session_age_seconds >= 0.0);
    assert_eq!(job.timing.index, 1);
    assert!(job.timing.session_age_seconds >= 0.0);
    let id = job.timing.candidate.question_id.clone();
    assert_eq!(job.timing.attempt, 1);
    s.finish(epoch, job, Err("private fake failure"));
    s.retry(1, first).unwrap();
    let retried = s.next(epoch).unwrap();
    assert_eq!(retried.timing.candidate.question_id, id);
    assert_eq!(retried.timing.attempt, 2);
    assert!(
        retried.timing.record("cue_ready")["queue_wait_ms"]
            .as_f64()
            .unwrap()
            >= 0.0
    );
    let serialized = retried.timing.record("cue_ready").to_string();
    assert!(!serialized.contains("integration") && !serialized.contains("private"));
    s.finish(epoch, retried, Ok(reply()));
    let next = s.next(epoch).unwrap();
    assert_eq!(next.id, second);
    assert_eq!(next.timing.index, 2);
    assert_ne!(next.timing.candidate.question_id, id);
    assert!(
        next.timing.record("cue_ready")["final_transcript_to_ready_ms"]
            .as_f64()
            .unwrap()
            >= 0.0
    );
}

#[test]
fn timing_intent_routes_do_not_change_routing() {
    tauri::async_runtime::block_on(async {
        let (s, epoch) = service();
        let mut router = worker::Router::default();
        router
            .process(
                candidate(
                    51,
                    "Tell me about your professional integration experience.",
                    Some("Tell me about your professional integration experience."),
                    1,
                ),
                &s,
                epoch,
                unavailable,
            )
            .await;
        let local = s.next(epoch).unwrap();
        assert_eq!(local.timing.intent_route, "local");
        assert!(!local.timing.intent_used);
        assert_eq!(local.timing.intent_request_ms, 0.0);
        s.finish(epoch, local, Ok(reply()));
        router
            .process(
                candidate(
                    52,
                    "Please discuss migration risks in this situation.",
                    None,
                    1,
                ),
                &s,
                epoch,
                action,
            )
            .await;
        let semantic = s.next(epoch).unwrap();
        assert_eq!(semantic.timing.intent_route, "gemini");
        assert!(semantic.timing.intent_used && semantic.timing.intent_request_ms >= 0.0);
        s.finish(epoch, semantic, Ok(reply()));
        router
            .process(
                candidate(53, "What was the result?", Some("What was the result?"), 1),
                &s,
                epoch,
                unavailable,
            )
            .await;
        let fallback = s.next(epoch).unwrap();
        assert_eq!(fallback.timing.intent_route, "fallback");
        assert!(fallback.timing.intent_used);
    });
}

#[test]
fn preparation_is_frozen_per_job_and_cleared_on_session_reset() {
    let (s, epoch) = service();
    s.set_preparation(Some(zeroize::Zeroizing::new(
        "fictional-signed-snapshot".into(),
    )));
    s.enqueue(epoch, None, request("How did you test the project?"));
    let job = s.next(epoch).expect("queued job");
    assert_eq!(
        job.preparation_token.as_deref().map(|s| s.as_str()),
        Some("fictional-signed-snapshot")
    );
    s.reset(Some(2));
    let epoch = s.lifecycle().0;
    s.enqueue(epoch, None, request("What happened next?"));
    assert!(s.next(epoch).unwrap().preparation_token.is_none());
    assert_eq!(
        job.preparation_token.as_deref().map(|s| s.as_str()),
        Some("fictional-signed-snapshot")
    );
}

#[test]
fn responding_remove_keeps_the_inflight_fifo_slot_until_completion() {
    let (s, epoch) = service();
    for question in ["Question one?", "Question two?", "Question three?"] {
        s.enqueue(epoch, None, request(question));
    }
    let one = s.next(epoch).unwrap();
    s.progress(epoch, &one, Some("I would clarify the goal."));
    assert_eq!(s.snapshot().unwrap().cards[0].status, "responding");
    assert!(s.next(epoch).is_none());
    s.remove(1, one.id).unwrap();
    assert_eq!(s.snapshot().unwrap().cards.len(), 2);
    assert!(s.next(epoch).is_none());
    s.finish(epoch, one, Ok(reply()));
    for id in [2, 3] {
        let job = s.next(epoch).unwrap();
        assert_eq!(job.id, id);
        s.finish(epoch, job, Ok(reply()));
    }
    assert_eq!(
        s.snapshot()
            .unwrap()
            .cards
            .iter()
            .map(|c| c.id)
            .collect::<Vec<_>>(),
        vec![2, 3]
    );
}
#[test]
fn partial_failure_retry_and_reset_keep_identity_and_discard_stale_text() {
    let (s, epoch) = service();
    s.enqueue(epoch, None, request("What happened next?"));
    let first = s.next(epoch).unwrap();
    let id = first.id;
    let qid = first.timing.candidate.question_id.clone();
    s.progress(epoch, &first, Some("I would clarify the goal."));
    s.finish(epoch, first, Err("Provider unavailable"));
    assert!(s.snapshot().unwrap().cards[0].answer.is_none());
    s.retry(1, id).unwrap();
    let retry = s.next(epoch).unwrap();
    assert_eq!(retry.timing.attempt, 2);
    assert_eq!(retry.timing.candidate.question_id, qid);
    s.progress(epoch, &retry, Some("I would check the plan."));
    assert_eq!(
        s.snapshot().unwrap().cards[0].answer.as_deref(),
        Some("I would check the plan.")
    );
    s.reset(Some(2));
    s.progress(epoch, &retry, Some("Stale text."));
    assert!(s.snapshot().unwrap().cards.is_empty());
}
#[test]
fn continuation_discards_obsolete_stream_progress_without_concurrent_jobs() {
    let (s, epoch) = service();
    let id = s
        .enqueue(epoch, None, request("Tell me about the project."))
        .unwrap();
    let old = s.next(epoch).unwrap();
    s.progress(epoch, &old, Some("I would clarify the goal."));
    s.enqueue(
        epoch,
        Some(id),
        request("Tell me about the project and challenges."),
    );
    s.progress(epoch, &old, Some("Obsolete draft."));
    assert!(s.snapshot().unwrap().cards[0].answer.is_none());
    assert!(s.next(epoch).is_none());
    s.finish(epoch, old, Ok(reply()));
    let next = s.next(epoch).unwrap();
    assert_eq!(next.id, id);
    assert!(next.input.question.contains("challenges"));
}

#[test]
fn stream_updates_are_published_without_ui_polling() {
    let (s, epoch) = service();
    let updates = std::sync::Arc::new(std::sync::Mutex::new(vec![]));
    let sink = updates.clone();
    s.set_publisher(std::sync::Arc::new(move |snapshot| {
        sink.lock().unwrap().push(snapshot)
    }));
    s.enqueue(epoch, None, request("How would you test the plan?"));
    let job = s.next(epoch).unwrap();
    s.progress(epoch, &job, Some("I would clarify the goal."));
    let view = updates.lock().unwrap().last().unwrap().clone();
    assert_eq!(view.cards[0].status, "responding");
    assert_eq!(view.cards[0].attempt, 1);
    assert!(view.cards[0].first_output_at_unix_ms.is_some());
    assert!(view.cards[0].ready_at_unix_ms.is_none());
    s.finish(epoch, job, Ok(reply()));
    assert_eq!(
        updates.lock().unwrap().last().unwrap().cards[0].status,
        "ready"
    );
}

#[test]
fn obvious_local_requests_bypass_semantic_provider_even_when_short_or_reassembled() {
    tauri::async_runtime::block_on(async {
        for (text, revision) in [
            ("Tell me about yourself.", 1),
            ("Describe your Salesforce experience.", 1),
            ("Who are you?", 1),
            ("How did you handle the Salesforce migration?", 2),
        ] {
            let (s, epoch) = service();
            let mut router = worker::Router::default();
            let local = crate::understanding::candidate::local_question(text, &[]);
            assert!(local.is_some(), "expected confident local detection");
            router
                .process(
                    candidate(1, text, local.as_deref(), revision),
                    &s,
                    epoch,
                    |_| async {
                        panic!("obvious request must not call Gemini Intent");
                        #[allow(unreachable_code)]
                        Err("unexpected call")
                    },
                )
                .await;
            let job = s.next(epoch).expect("immediately queued locally");
            assert_eq!(job.timing.intent_route, "local");
            assert!(!job.timing.intent_used);
            assert_eq!(job.timing.intent_request_ms, 0.0);
        }
    });
}

#[test]
fn ambiguous_and_contextual_requests_still_use_semantic_provider() {
    tauri::async_runtime::block_on(async {
        for (text, local) in [
            ("Please discuss migration risks in this situation.", None),
            ("What was the result?", Some("What was the result?")),
            ("Why?", Some("Why?")),
            ("Can you explain that?", Some("Can you explain that?")),
        ] {
            let (s, epoch) = service();
            let mut router = worker::Router::default();
            router
                .process(candidate(1, text, local, 1), &s, epoch, action)
                .await;
            let job = s.next(epoch).expect("semantic request queued");
            assert_eq!(job.timing.intent_route, "gemini");
            assert!(job.timing.intent_used);
        }
    });
}

fn code_reply() -> transport::CueReply {
    transport::CueReply {
        code_assist: Some(transport::CodeAssist {
            language: "Python".into(),
            approach: "Track seen values.".into(),
            code: "def duplicates(values):\n    return []\n".into(),
            complexity: None,
            what_to_say: "I track seen values.".into(),
        }),
        ..reply()
    }
}

#[test]
fn coding_followups_queue_fifo_use_validated_solution_and_survive_remove() {
    let (s, epoch) = service();
    let first = s
        .enqueue(
            epoch,
            None,
            request("Write a function that finds duplicates in an array."),
        )
        .unwrap();
    let q1 = s.next(epoch).unwrap();
    assert_eq!(q1.input.cue_kind, "code");
    let second = s
        .enqueue(epoch, None, request("Can you optimize that solution?"))
        .unwrap();
    let third = s
        .enqueue(epoch, None, request("Can you do it without extra space?"))
        .unwrap();
    assert!(s.next(epoch).is_none());
    let code = code_reply().code_assist.unwrap();
    s.progress_code(epoch, &q1, Some("Track seen values."), Some(&code));
    s.remove(1, first).unwrap();
    assert!(s.next(epoch).is_none());
    s.finish(epoch, q1, Ok(code_reply()));
    let q2 = s.next(epoch).unwrap();
    assert_eq!(q2.id, second);
    let context = q2.input.coding_context.as_ref().unwrap();
    assert!(context.problem.contains("duplicates"));
    assert_eq!(context.language, "Python");
    assert!(context.code.contains("def duplicates"));
    s.finish(epoch, q2, Ok(code_reply()));
    let q3 = s.next(epoch).unwrap();
    assert_eq!(q3.id, third);
    assert!(q3.input.coding_context.is_some());
    s.finish(epoch, q3, Ok(code_reply()));
    assert_eq!(s.snapshot().unwrap().cards.len(), 2);
    s.enqueue(epoch, None, request("Tell me about yourself."));
    assert!(!s.has_coding_context(epoch));
    s.reset(None);
    assert!(!s.has_coding_context(s.lifecycle().0));
    assert!(s.snapshot().unwrap().cards.is_empty());
}

#[test]
fn code_partial_failure_retry_preserves_identity_and_clears_draft() {
    let (s, epoch) = service();
    s.enqueue(
        epoch,
        None,
        request("Write an Apex trigger to prevent duplicate Contacts."),
    );
    let job = s.next(epoch).unwrap();
    let id = job.id;
    let question_id = job.timing.candidate.question_id.clone();
    let code = code_reply().code_assist.unwrap();
    s.progress_code(epoch, &job, Some("Draft approach."), Some(&code));
    assert_eq!(s.snapshot().unwrap().cards[0].status, "responding");
    s.finish(epoch, job, Err("Provider unavailable"));
    assert!(s.snapshot().unwrap().cards[0].code_assist.is_none());
    s.retry(1, id).unwrap();
    let retried = s.next(epoch).unwrap();
    assert_eq!(retried.timing.candidate.question_id, question_id);
    assert_eq!(retried.timing.attempt, 2);
    assert!(s.snapshot().unwrap().cards[0].code_assist.is_none());
    s.finish(epoch, retried, Ok(code_reply()));
    assert!(s.snapshot().unwrap().cards[0].code_assist.is_some());
}

#[test]
fn obvious_coding_requests_and_followups_bypass_gemini_intent() {
    tauri::async_runtime::block_on(async {
        let (s, epoch) = service();
        let mut router = worker::Router::default();
        for (id, text) in [
            (1, "Write a function that finds duplicates in an array."),
            (2, "Can you optimize that solution?"),
            (3, "Can you do it without extra space?"),
        ] {
            router
                .process(candidate(id, text, None, 1), &s, epoch, |_| async {
                    panic!("Obvious code requests must be local");
                    #[allow(unreachable_code)]
                    Err("unexpected")
                })
                .await;
        }
        assert_eq!(s.snapshot().unwrap().cards.len(), 3);
        let first = s.next(epoch).unwrap();
        assert_eq!(first.timing.intent_route, "local");
        assert!(!first.timing.intent_used);
    });
}

#[test]
fn repeated_coding_followup_is_deduplicated_per_problem_not_across_problems() {
    tauri::async_runtime::block_on(async {
        let (s, epoch) = service();
        let mut router = worker::Router::default();
        for (id, text) in [
            (1, "Write a function to find duplicates in an array."),
            (2, "Can you optimize that solution?"),
            (3, "Can you optimize that solution?"),
            (4, "How would you reverse a linked list?"),
            (5, "Can you optimize that solution?"),
        ] {
            router
                .process(candidate(id, text, None, 1), &s, epoch, unavailable)
                .await;
        }
        assert_eq!(s.snapshot().unwrap().cards.len(), 4);
    });
}
