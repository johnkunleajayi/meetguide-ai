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

#[test]
fn clear_only_dismisses_the_matching_cue_and_keeps_session_eligible() {
    let service = CueService::default();
    service.reset(Some(1));
    let (old, cancelled) = service.begin(1, 1, false).unwrap();
    service.finish(old, Ok(reply()));
    service.clear(2, 1).unwrap();
    assert_eq!(service.snapshot().unwrap().status, "ready");
    service.clear(1, 1).unwrap();
    assert!(cancelled.has_changed().unwrap());
    assert_eq!(service.snapshot().unwrap().status, "idle");
    assert!(service.snapshot().unwrap().answer.is_none());
    service.finish(old, Ok(reply()));
    assert!(service.snapshot().unwrap().answer.is_none());
    assert!(service.begin(1, 1, false).is_none());
    let (new, _) = service.begin(1, 2, false).unwrap();
    service.clear(1, 1).unwrap(); // Late Clear cannot dismiss a newer question.
    service.finish(new, Ok(reply()));
    assert_eq!(service.snapshot().unwrap().event_id, 2);
    assert_eq!(service.snapshot().unwrap().status, "ready");
}

#[test]
fn completed_answer_never_blocks_a_later_question() {
    let service = CueService::default();
    service.reset(Some(1));
    let (first, _) = service.begin(1, 1, false).unwrap();
    service.finish(first, Ok(reply()));
    let (next, _) = service.begin(1, 2, false).unwrap();
    assert!(service.snapshot().unwrap().answer.is_none());
    service.finish(next, Ok(reply()));
    assert_eq!(service.snapshot().unwrap().event_id, 2);
}

#[tokio::test(flavor = "current_thread")]
async fn only_latest_waiting_question_runs_after_active_request_drains() {
    let service = Arc::new(CueService::default());
    service.reset(Some(1));
    let (first, cancelled) = service.begin(1, 1, false).unwrap();
    let (started_tx, started_rx) = tokio::sync::oneshot::channel();
    let (finish_tx, finish_rx) = tokio::sync::oneshot::channel();
    let worker = service.clone();
    let active = tokio::spawn(async move {
        worker
            .run(first, cancelled, || async {
                started_tx.send(()).unwrap();
                finish_rx.await.unwrap();
                Ok(reply())
            })
            .await
    });
    started_rx.await.unwrap();
    let (second, cancelled) = service.begin(1, 2, false).unwrap();
    let worker = service.clone();
    let obsolete = tokio::spawn(async move {
        worker
            .run(second, cancelled, || async {
                panic!("superseded waiter must not send")
            })
            .await
    });
    let (latest, cancelled) = service.begin(1, 3, false).unwrap();
    let (sent_tx, mut sent_rx) = tokio::sync::oneshot::channel();
    let worker = service.clone();
    let waiting = tokio::spawn(async move {
        let result = worker
            .run(latest, cancelled, || async {
                sent_tx.send(()).unwrap();
                Ok(reply())
            })
            .await;
        worker.finish(latest, result.unwrap());
    });
    tokio::task::yield_now().await;
    assert!(matches!(
        sent_rx.try_recv(),
        Err(tokio::sync::oneshot::error::TryRecvError::Empty)
    ));
    assert!(obsolete.await.unwrap().is_none());
    finish_tx.send(()).unwrap();
    service.finish(first, active.await.unwrap().unwrap());
    waiting.await.unwrap();
    assert_eq!(service.snapshot().unwrap().event_id, 3);
    assert_eq!(service.snapshot().unwrap().status, "ready");
}

#[test]
fn clearing_does_not_stop_audio_transcription_or_understanding() {
    let audio = crate::audio::AudioService::default();
    let mut store = audio.transcript.lock().unwrap();
    store.reset(&[crate::transcription::Source::System]);
    store.snapshot.understanding.events.push_back(event());
    let session = store.snapshot.session_id;
    let before = serde_json::to_value(&store.snapshot).unwrap();
    drop(store);
    let audio_before = serde_json::to_value(audio.status().unwrap()).unwrap();
    audio.cues.reset(Some(session));
    let (seq, _) = audio.cues.begin(session, 1, false).unwrap();
    audio.cues.finish(seq, Ok(reply()));
    audio.cues.clear(session, 1).unwrap();
    assert_eq!(
        before,
        serde_json::to_value(&audio.transcript.lock().unwrap().snapshot).unwrap()
    );
    assert_eq!(
        audio_before,
        serde_json::to_value(audio.status().unwrap()).unwrap()
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
}
