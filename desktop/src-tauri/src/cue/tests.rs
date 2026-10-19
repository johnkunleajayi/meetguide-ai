use super::*;
use crate::understanding::domain::ConversationTurn;

fn event() -> MeaningfulEvent {
    MeaningfulEvent {
        id: 1,
        event_type: EventType::Question,
        speaker: Speaker::Them,
        text: "How did you handle the migration?".into(),
        confidence: 0.94,
        turn_id: 1,
        detected_at_ms: 0,
        context: vec![],
    }
}
fn reply() -> transport::CueReply {
    transport::CueReply {
        answer: "A prepared answer.\n\nAnother paragraph.".into(),
        grounding: "general_approach".into(),
        sources: vec![],
    }
}
#[test]
fn only_confident_final_question_events_become_inputs() {
    let mut item = event();
    assert!(input(&item).is_some());
    item.speaker = Speaker::You;
    assert!(input(&item).is_none());
    item.speaker = Speaker::Them;
    item.event_type = EventType::ImportantPoint;
    assert!(input(&item).is_none());
    item.event_type = EventType::Question;
    item.confidence = 0.7;
    assert!(input(&item).is_none());
    item.confidence = f32::NAN;
    assert!(input(&item).is_none());
}
#[test]
fn input_bounds_conversation_and_preserves_sources() {
    let mut item = event();
    item.context = (0..20)
        .map(|id| ConversationTurn {
            id,
            speaker: if id % 2 == 0 {
                Speaker::Them
            } else {
                Speaker::You
            },
            text: "é".repeat(3000),
            started_at_ms: id,
            last_segment_at_ms: id,
            epoch: 1,
            revision: 1,
        })
        .collect();
    let request = input(&item).unwrap();
    assert!(request.context.len() <= 6);
    assert!(
        request
            .context
            .iter()
            .map(|turn| turn.text.chars().count())
            .sum::<usize>()
            <= 4000
    );
    assert!(request.context.iter().any(|turn| turn.speaker == "you"));
    assert!(request.finalized && request.event_type == "question");
}
#[test]
fn duplicates_do_not_generate_and_retry_is_explicit() {
    let service = CueService::default();
    service.reset(Some(1));
    let (first, _) = service.begin(1, 1, false).unwrap();
    assert!(service.begin(1, 1, false).is_none());
    service.finish(first, Err("Retryable failure"));
    assert!(service.begin(1, 1, false).is_none());
    let (retry, _) = service.begin(1, 1, true).unwrap();
    service.finish(retry, Ok(reply()));
    assert!(service.begin(1, 1, true).is_none());
    assert_eq!(service.snapshot().unwrap().status, "ready");
}
#[test]
fn supersession_cancels_old_work_and_rejects_stale_completion() {
    let service = CueService::default();
    service.reset(Some(1));
    let (old, cancel) = service.begin(1, 1, false).unwrap();
    let (new, _) = service.begin(1, 2, false).unwrap();
    assert!(cancel.has_changed().unwrap());
    service.finish(old, Ok(reply()));
    assert_eq!(service.snapshot().unwrap().status, "preparing");
    service.finish(new, Ok(reply()));
    assert_eq!(service.snapshot().unwrap().event_id, 2);
}
#[test]
fn stop_restart_and_logout_clear_answers_and_cancel_pending_work() {
    let service = CueService::default();
    service.reset(Some(1));
    let (old, cancel) = service.begin(1, 1, false).unwrap();
    service.reset(None);
    assert!(cancel.has_changed().unwrap());
    service.finish(old, Ok(reply()));
    assert!(service.snapshot().unwrap().answer.is_none());
    assert!(service.begin(1, 1, false).is_none());
    service.reset(Some(2));
    assert!(service.begin(1, 1, false).is_none());
    let (fresh, _) = service.begin(2, 1, false).unwrap();
    service.finish(fresh, Ok(reply()));
    service.reset(None);
    assert!(service.snapshot().unwrap().answer.is_none());
}
#[test]
fn transcript_reset_or_new_question_invalidates_completion() {
    let mut store = crate::transcription::TranscriptStore::default();
    store.reset(&[crate::transcription::Source::System]);
    store.snapshot.understanding.events.push_back(event());
    let session = store.snapshot.session_id;
    assert!(current(&store, session, 1));
    let mut next = event();
    next.id = 2;
    store.snapshot.understanding.events.push_back(next);
    assert!(!current(&store, session, 1));
    store.stop_understanding();
    assert!(!current(&store, session, 2));
    store.reset(&[]);
    assert!(!current(&store, session, 2));
}
