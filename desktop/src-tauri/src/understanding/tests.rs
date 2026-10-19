use super::*;
fn engine() -> UnderstandingEngine {
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    e
}
fn say(e: &mut UnderstandingEngine, speaker: Speaker, id: u64, text: &str, now: u64) {
    e.finalized(speaker, 1, id, text, now, now);
}
#[test]
fn fragments_merge_and_wait_for_complete_speech() {
    let mut e = engine();
    say(&mut e, Speaker::Them, 1, "Can you explain", 0);
    assert!(!e.tick(1200));
    say(
        &mut e,
        Speaker::Them,
        2,
        "how you handled that project?",
        1500,
    );
    assert_eq!(e.snapshot.turns.len(), 1);
    assert!(!e.tick(2699));
    assert!(e.tick(2700));
    assert_eq!(
        e.snapshot.events[0].text,
        "Can you explain how you handled that project?"
    );
}
#[test]
fn sources_pauses_epochs_and_connection_gaps_separate_turns() {
    let mut e = engine();
    say(&mut e, Speaker::Them, 1, "First statement.", 0);
    say(&mut e, Speaker::You, 1, "My reply.", 100);
    say(&mut e, Speaker::Them, 2, "Another statement.", 200);
    assert_eq!(e.snapshot.turns.len(), 3);
    e.interim(Speaker::Them, "New", 5000);
    say(&mut e, Speaker::Them, 3, "New speech.", 5100);
    assert_eq!(e.snapshot.turns.len(), 4);
    e.finalized(Speaker::Them, 2, 1, "Reconnected speech.", 5200, 5200);
    assert_eq!(e.snapshot.turns.len(), 5);
    e.gap(Speaker::Them);
    say(&mut e, Speaker::Them, 4, "After a gap.", 5300);
    assert_eq!(e.snapshot.turns.len(), 6);
}
#[test]
fn direct_and_unpunctuated_questions() {
    for text in [
        "Tell me about yourself.",
        "Can you explain how you handled that project?",
        "What would you do differently",
        "Why did you choose Salesforce",
        "How did you handle the migration?",
        "Are you comfortable leading this project?",
    ] {
        let mut e = engine();
        say(&mut e, Speaker::Them, 1, text, 0);
        assert!(e.tick(1200), "{text}");
        assert!(e.snapshot.events[0].confidence >= THRESHOLD);
    }
}
#[test]
fn non_questions_and_incomplete_fragments_are_quiet() {
    for text in [
        "We chose Salesforce for the migration.",
        "How we handled it was successful.",
        "What we did was automate it.",
        "Can you explain",
        "What would you",
        "Tell me about",
        "How did you handle the",
        "Can you explain how",
        "Why did you choose...",
        "This is a statement?",
    ] {
        let mut e = engine();
        say(&mut e, Speaker::Them, 1, text, 0);
        assert!(!e.tick(1200), "{text}");
    }
    let mut e = engine();
    say(&mut e, Speaker::You, 1, "Why did you choose Salesforce?", 0);
    assert!(!e.tick(1200));
}
#[test]
fn interim_speech_blocks_pending_question() {
    let mut e = engine();
    e.interim(Speaker::Them, "Why did you choose Salesforce?", 0);
    assert!(!e.tick(5000));
    say(
        &mut e,
        Speaker::Them,
        1,
        "Why did you choose Salesforce?",
        5100,
    );
    e.interim(Speaker::Them, "for", 5200);
    assert!(!e.tick(20000));
    e.interim(Speaker::Them, "for this", 20000);
    say(&mut e, Speaker::Them, 2, "for this project?", 20100);
    assert!(e.tick(21300));
}
#[test]
fn duplicates_and_cooldown_are_suppressed() {
    let mut e = engine();
    say(
        &mut e,
        Speaker::Them,
        1,
        "Can you explain the migration?",
        0,
    );
    assert!(e.tick(1200));
    say(
        &mut e,
        Speaker::Them,
        1,
        "Can you explain the migration?",
        9000,
    );
    say(
        &mut e,
        Speaker::Them,
        2,
        "Could you explain migration",
        10000,
    );
    assert!(!e.tick(11200));
    say(
        &mut e,
        Speaker::Them,
        3,
        "What would you do differently?",
        12000,
    );
    assert!(e.tick(13200));
    say(
        &mut e,
        Speaker::Them,
        4,
        "Why did you choose Salesforce?",
        16000,
    );
    assert!(!e.tick(17200));
    say(
        &mut e,
        Speaker::Them,
        5,
        "How did you manage the team?",
        21000,
    );
    assert!(e.tick(22200));
    assert_eq!(e.snapshot.events.len(), 3);
}
#[test]
fn context_and_event_memory_are_bounded() {
    let mut e = engine();
    for id in 0..1000 {
        say(
            &mut e,
            if id % 2 == 0 {
                Speaker::Them
            } else {
                Speaker::You
            },
            id,
            &format!("Statement {id} {}", "é".repeat(1500)),
            id * 4000,
        );
    }
    assert!(e.snapshot.turns.len() <= MAX_TURNS);
    assert!(e.snapshot.turns.iter().map(|t| t.text.len()).sum::<usize>() <= MAX_CONTEXT_BYTES);
    assert!(e.snapshot.trimmed_turns > 0);
    assert!(e.seen.len() <= 512);
    for id in 1000..1140 {
        say(
            &mut e,
            Speaker::Them,
            id,
            &format!("Why did you choose project {id}?"),
            id * 8000,
        );
        assert!(e.tick(id * 8000 + 1200));
    }
    assert_eq!(e.snapshot.events.len(), 8);
    assert_eq!(e.fingerprints.len(), 128);
    let event = e.snapshot.events.back().unwrap();
    assert!(event.context.len() <= 8);
    assert!(event.context.iter().map(|t| t.text.len()).sum::<usize>() <= 6000);
}
#[test]
fn context_preserves_sources_and_is_frozen() {
    let mut e = engine();
    say(&mut e, Speaker::You, 1, "I led the migration.", 0);
    say(
        &mut e,
        Speaker::Them,
        1,
        "How did you handle the migration?",
        100,
    );
    assert!(e.tick(1300));
    assert!(e.snapshot.events[0].context[0].speaker == Speaker::You);
    say(&mut e, Speaker::Them, 2, "More words.", 1400);
    assert!(!e.snapshot.events[0].context[1].text.contains("More words"));
}
#[test]
fn stop_reset_and_logout_clear_processing_state() {
    let mut e = engine();
    say(&mut e, Speaker::Them, 1, "Tell me about yourself.", 0);
    e.stop();
    assert!(!e.tick(1200));
    say(&mut e, Speaker::You, 1, "Trailing final.", 1300);
    assert_eq!(e.snapshot.turns.len(), 1);
    e.reset(true);
    assert!(e.snapshot.turns.is_empty());
    say(&mut e, Speaker::Them, 1, "Tell me about yourself.", 0);
    assert!(e.tick(1200));
    e.reset(false);
    assert!(e.snapshot.events.is_empty() && e.snapshot.turns.is_empty());
    say(&mut e, Speaker::Them, 1, "Tell me about yourself.", 0);
    assert!(!e.tick(1200));
    e.reset(true);
    say(&mut e, Speaker::Them, 1, "Tell me about yourself.", 0);
    assert!(e.tick(1200));
}
#[test]
fn oversized_unicode_turns_are_bounded_and_not_detected_when_clipped() {
    let mut e = engine();
    say(
        &mut e,
        Speaker::Them,
        1,
        &format!("Why did you choose {}", "é".repeat(4000)),
        0,
    );
    assert!(e.snapshot.turns[0].text.len() <= MAX_TURN_BYTES);
    assert!(!e.tick(1200));
}
struct WeakProvider;
impl UnderstandingProvider for WeakProvider {
    fn analyze(&self, t: &ConversationTurn, _: &[ConversationTurn]) -> Option<Detection> {
        Some(Detection {
            event_type: EventType::Question,
            text: t.text.clone(),
            confidence: 0.5,
        })
    }
}
#[test]
fn confidence_threshold_is_enforced() {
    let mut e = UnderstandingEngine::new(WeakProvider);
    e.reset(true);
    e.finalized(Speaker::Them, 1, 1, "Tell me about yourself.", 0, 0);
    assert!(!e.tick(1200));
}
