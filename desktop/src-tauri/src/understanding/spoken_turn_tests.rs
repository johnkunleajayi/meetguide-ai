use super::*;

const FIRST: &str = "Tell me about a Salesforce integration you worked on.";
const SECOND: &str = "And challenges you faced.";
const WHOLE: &str =
    "Tell me about a Salesforce integration you worked on and challenges you faced.";
fn engine() -> UnderstandingEngine {
    let mut e = UnderstandingEngine::default();
    e.reset(true);
    e
}
fn final_at(e: &mut UnderstandingEngine, speaker: Speaker, segment: u64, text: &str, now: u64) {
    e.finalized(speaker, 1, segment, text, now, now);
}

#[test]
fn split_salesforce_request_matches_single_final_and_emits_one_event() {
    let mut whole = engine();
    final_at(&mut whole, Speaker::Them, 1, WHOLE, 0);
    assert!(whole.tick(1200));
    let mut split = engine();
    final_at(&mut split, Speaker::Them, 1, FIRST, 0);
    final_at(&mut split, Speaker::Them, 2, SECOND, 600);
    assert!(
        split.tick(1800),
        "split finals must produce the same request as the single final"
    );
    assert_eq!(split.snapshot.events.len(), 1);
    assert_eq!(
        detector::fingerprint(&split.snapshot.events[0].text),
        detector::fingerprint(WHOLE)
    );
}

#[test]
fn standalone_relative_clause_is_complete_but_unfinished_objects_are_not() {
    let mut e = engine();
    final_at(&mut e, Speaker::Them, 1, FIRST, 0);
    assert!(e.tick(1200));
    for fragment in [
        "Tell me about the integration with.",
        "How did you handle the",
        "Tell me about",
    ] {
        let mut quiet = engine();
        final_at(&mut quiet, Speaker::Them, 1, fragment, 0);
        assert!(!quiet.tick(1200), "{fragment}");
    }
}

#[test]
fn short_linked_requests_preserve_all_parts() {
    for (first, second) in [
        (
            "Walk me through your Salesforce experience.",
            "Especially Service Cloud.",
        ),
        (
            "How did you handle the migration?",
            "And what would you do differently?",
        ),
        ("Describe the project.", "What was your role?"),
        ("Tell me about the implementation.", "How did you test it?"),
    ] {
        let mut e = engine();
        final_at(&mut e, Speaker::Them, 1, first, 0);
        final_at(&mut e, Speaker::Them, 2, second, 700);
        assert!(e.tick(1900), "{first} / {second}");
        assert_eq!(e.snapshot.turns.len(), 1);
        assert_eq!(e.snapshot.events.len(), 1);
        let all_words = detector::fingerprint(&format!("{first} {second}"));
        assert_eq!(detector::fingerprint(&e.snapshot.events[0].text), all_words);
    }
}

#[test]
fn continuation_after_detection_enriches_one_logical_event_without_cooldown_delay() {
    let mut e = engine();
    final_at(&mut e, Speaker::Them, 1, FIRST, 0);
    assert!(e.tick(1200));
    let old = e.snapshot.events[0].id;
    let turn = e.snapshot.events[0].turn_id;
    final_at(&mut e, Speaker::Them, 2, SECOND, 1600);
    assert!(!e.tick(2799));
    assert!(e.tick(2800));
    assert_eq!(e.snapshot.events.len(), 1);
    assert_eq!(e.snapshot.events[0].turn_id, turn);
    assert_ne!(e.snapshot.events[0].id, old); // Existing newest-question scheduler invalidates old results.
    assert_eq!(
        detector::fingerprint(&e.snapshot.events[0].text),
        detector::fingerprint(WHOLE)
    );
    assert!(!e.tick(10000));
}

#[test]
fn answer_pause_gap_epoch_or_fresh_command_separates_requests() {
    let mut e = engine();
    final_at(
        &mut e,
        Speaker::Them,
        1,
        "Tell me about the integration.",
        0,
    );
    assert!(e.tick(1200));
    final_at(
        &mut e,
        Speaker::You,
        1,
        "I tested the API exchanges in a sandbox.",
        1400,
    );
    final_at(
        &mut e,
        Speaker::Them,
        2,
        "What was the biggest challenge?",
        1700,
    );
    assert!(e.tick(2900));
    assert!(!e.tick(7200));
    assert_eq!(e.snapshot.events.len(), 2);
    assert_ne!(e.snapshot.events[0].turn_id, e.snapshot.events[1].turn_id);
    assert_eq!(e.snapshot.events[1].text, "What was the biggest challenge?");
    for boundary in 0..4 {
        let mut e = engine();
        final_at(&mut e, Speaker::Them, 1, FIRST, 0);
        assert!(e.tick(1200));
        match boundary {
            0 => final_at(&mut e, Speaker::Them, 2, SECOND, MERGE_GAP_MS + 1),
            1 => {
                e.gap(Speaker::Them);
                final_at(&mut e, Speaker::Them, 2, SECOND, 1600);
            }
            2 => e.finalized(Speaker::Them, 2, 1, SECOND, 1600, 1600),
            _ => final_at(
                &mut e,
                Speaker::Them,
                2,
                "Tell me about your leadership experience.",
                1600,
            ),
        }
        assert_eq!(e.snapshot.turns.len(), 2);
    }
}

#[test]
fn an_interim_answer_also_prevents_merging_across_the_user() {
    let mut e = engine();
    final_at(&mut e, Speaker::Them, 1, FIRST, 0);
    assert!(e.tick(1200));
    e.interim(Speaker::You, "I tested the API", 1300);
    final_at(
        &mut e,
        Speaker::Them,
        2,
        "And what would you do differently?",
        1700,
    );
    assert_eq!(e.snapshot.turns.len(), 2);
}

#[test]
fn ordinary_statements_connectors_and_acknowledgements_do_not_become_questions() {
    for fragment in [
        "okay",
        "right",
        "I see",
        "interesting",
        "and",
        "How",
        "Why",
        "Especially Service Cloud.",
    ] {
        let mut e = engine();
        final_at(&mut e, Speaker::Them, 1, "We migrated the records.", 0);
        final_at(&mut e, Speaker::Them, 2, fragment, 300);
        final_at(
            &mut e,
            Speaker::Them,
            3,
            "We tested the API exchanges.",
            600,
        );
        assert!(!e.tick(1800), "{fragment}");
        assert!(e.snapshot.events.is_empty());
    }
    let mut e = engine();
    final_at(&mut e, Speaker::You, 1, FIRST, 0);
    final_at(&mut e, Speaker::You, 2, SECOND, 600);
    assert!(!e.tick(1800));
}

#[test]
fn repeated_playback_and_different_segmentation_deduplicate_but_not_forever() {
    let mut e = engine();
    final_at(&mut e, Speaker::Them, 1, FIRST, 0);
    final_at(&mut e, Speaker::Them, 2, SECOND, 600);
    assert!(e.tick(1800));
    // Identical immutable ASR IDs and new IDs from repeated playback are both quiet.
    final_at(&mut e, Speaker::Them, 2, SECOND, 900);
    assert!(!e.tick(2100));
    for (id, time, text) in [(3, 5000, FIRST), (4, 5600, SECOND), (5, 10000, WHOLE)] {
        final_at(&mut e, Speaker::Them, id, text, time);
        assert!(!e.tick(time + 1200));
    }
    assert_eq!(e.snapshot.events.len(), 1);
    final_at(&mut e, Speaker::Them, 6, WHOLE, DUPLICATE_MS + 3000);
    assert!(e.tick(DUPLICATE_MS + 4200));
    assert_eq!(e.snapshot.events.len(), 2);
}

#[test]
fn contextual_short_followups_remain_distinct_after_an_answer() {
    for text in [
        "Why?",
        "How?",
        "What happened next?",
        "What was the result?",
        "Can you explain that?",
    ] {
        let mut e = engine();
        final_at(&mut e, Speaker::Them, 1, FIRST, 0);
        assert!(e.tick(1200));
        final_at(
            &mut e,
            Speaker::You,
            1,
            "I tested the API exchanges in a sandbox.",
            2000,
        );
        final_at(&mut e, Speaker::Them, 2, text, 8000);
        assert!(e.tick(9200), "{text}");
        assert_eq!(e.snapshot.events.len(), 2);
        assert_eq!(e.snapshot.events[1].text, text);
    }
}

#[test]
fn second_real_question_must_not_be_lost_after_undo_fragment() {
    let mut e = engine();
    final_at(&mut e, Speaker::Them, 1, FIRST, 0);
    final_at(&mut e, Speaker::Them, 2, SECOND, 600);
    assert!(e.tick(1800));
    final_at(&mut e, Speaker::Them, 3, "How did you undo", 8000);
    final_at(&mut e, Speaker::Them, 4, "the Salesforce migration?", 8600);
    assert!(e.tick(9800), "the second assembled question must survive");
    assert_eq!(e.snapshot.events.len(), 2);
    assert_eq!(
        e.snapshot.events[1].text,
        "How did you undo the Salesforce migration?"
    );
}
