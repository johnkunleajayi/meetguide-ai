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
fn duplicates_are_suppressed_while_distinct_questions_continue() {
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
    assert!(e.tick(17200));
    say(
        &mut e,
        Speaker::Them,
        5,
        "How did you manage the team?",
        21000,
    );
    assert!(e.tick(22200));
    assert_eq!(e.snapshot.events.len(), 4);
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
    assert!(e.fingerprints.len() <= 128);
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

#[test]
fn short_follow_ups_use_context_but_fragments_stay_quiet() {
    for text in [
        "Why?",
        "How did you solve that?",
        "What happened next?",
        "What was the result?",
        "Can you explain that?",
    ] {
        let mut e = engine();
        say(
            &mut e,
            Speaker::You,
            1,
            "I worked on the Salesforce integration.",
            0,
        );
        say(&mut e, Speaker::Them, 1, text, 100);
        assert!(e.tick(1300), "{text}");
        assert!(e.snapshot.events[0]
            .context
            .iter()
            .any(|t| t.speaker == Speaker::You));
    }
    for text in [
        "Why",
        "Can you explain",
        "How did you",
        "What happened",
        "that?",
    ] {
        let mut e = engine();
        say(
            &mut e,
            Speaker::You,
            1,
            "I worked on the Salesforce integration.",
            0,
        );
        say(&mut e, Speaker::Them, 1, text, 100);
        assert!(!e.tick(1300), "{text}");
    }
    let mut e = engine();
    say(&mut e, Speaker::Them, 1, "Why?", 0);
    assert!(!e.tick(1200)); // No referent in an empty conversation.
}

#[test]
fn distinct_followup_is_emitted_without_destructive_cooldown() {
    let mut e = engine();
    say(&mut e, Speaker::Them, 1, "Tell me about the migration.", 0);
    assert!(e.tick(1200));
    say(
        &mut e,
        Speaker::You,
        1,
        "I mapped the records and tested the exchanges.",
        1400,
    );
    say(&mut e, Speaker::Them, 2, "What was the result?", 2000);
    assert!(e.tick(3200));
    assert!(!e.tick(7199));
    assert!(!e.tick(7200));
    assert_eq!(
        e.snapshot.events.back().unwrap().text,
        "What was the result?"
    );
    assert!(!e.tick(9000));
}

#[test]
fn repeated_why_is_suppressed_until_a_different_answer_supplies_context() {
    let mut e = engine();
    say(
        &mut e,
        Speaker::You,
        1,
        "I chose Salesforce for the integration.",
        0,
    );
    say(&mut e, Speaker::Them, 1, "Why?", 100);
    assert!(e.tick(1300));
    say(&mut e, Speaker::Them, 2, "Why?", 11000);
    assert!(!e.tick(12200));
    say(
        &mut e,
        Speaker::You,
        2,
        "Its API supported the required data exchanges.",
        13000,
    );
    say(&mut e, Speaker::Them, 3, "Why?", 14000);
    assert!(e.tick(15200));
}

#[test]
fn scenario_and_interview_requests_preserve_complete_context() {
    for text in [
        "Can you give us a specific example of a time when you mentored or developed others, what you did, and what impact your approach had?",
        "Suppose participation is high. As the lead, how would you respond?",
        "Imagine the launch fails, what would you do if funding stopped?",
        "Tell me about a time you developed others.",
        "Walk me through your mentoring approach.",
        "Describe your leadership approach.",
        "What would you do if participation dropped?",
        "How would you respond to unhappy mentees?",
    ] {
        let mut e = engine();
        say(&mut e, Speaker::Them, 1, text, 0);
        assert!(e.tick(1200), "{text}");
        assert_eq!(e.snapshot.events.len(), 1);
        assert_eq!(e.snapshot.events[0].text, text);
    }
}
