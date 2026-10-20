pub(crate) use super::detector::fingerprint;
use super::detector::{words, LocalQuestionDetector};
use super::domain::*;

#[derive(Clone)]
pub struct Candidate {
    pub timing: crate::timing::CandidateTiming,
    pub turn_id: u64,
    pub revision: u64,
    pub text: String,
    pub context: Vec<ConversationTurn>,
    pub local: Option<String>,
}

pub fn meaningful(turn: &ConversationTurn) -> bool {
    if turn.speaker != Speaker::Them || turn.text.chars().count() > 1600 || turn.text.ends_with('…')
    {
        return false;
    }
    let key = fingerprint(&turn.text);
    let tokens = words(&turn.text);
    !tokens.is_empty()
        && !key.is_empty()
        && !matches!(
            key.as_str(),
            "okay"
                | "ok"
                | "right"
                | "i see"
                | "interesting"
                | "yes"
                | "no"
                | "thanks"
                | "thank you"
                | "um"
                | "uh"
                | "and"
                | "but"
                | "also"
        )
        && (tokens.len() >= 3 || turn.text.ends_with('?'))
}

pub fn local_question(text: &str, context: &[ConversationTurn]) -> Option<String> {
    let turn = ConversationTurn {
        id: u64::MAX,
        speaker: Speaker::Them,
        text: text.into(),
        started_at_ms: 0,
        last_segment_at_ms: 0,
        epoch: 0,
        revision: 1,
    };
    LocalQuestionDetector
        .analyze(&turn, context)
        .filter(|d| d.confidence >= 0.82)
        .map(|d| d.text)
}
pub fn keys(text: &str) -> Vec<String> {
    super::assembly::prefix_keys(text)
}
