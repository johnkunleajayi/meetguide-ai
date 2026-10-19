//! Provider-independent conversation domain. No persistence or network behavior.
use serde::Serialize;
use std::collections::VecDeque;

#[derive(Clone, Copy, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Speaker {
    Them,
    You,
}
impl Speaker {
    pub(crate) fn index(self) -> usize {
        if self == Self::Them {
            0
        } else {
            1
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConversationTurn {
    pub id: u64,
    pub speaker: Speaker,
    pub text: String,
    pub started_at_ms: u64,
    pub last_segment_at_ms: u64,
    #[serde(skip)]
    pub(crate) epoch: u64,
    #[serde(skip)]
    pub(crate) revision: u64,
}

#[allow(dead_code)] // Reserved domain types; only Question is emitted in this milestone.
#[derive(Clone, Copy, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EventType {
    Question,
    FollowUpOpportunity,
    ClarificationOpportunity,
    AskOpportunity,
    ImportantPoint,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MeaningfulEvent {
    pub id: u64,
    #[serde(rename = "type")]
    pub event_type: EventType,
    pub speaker: Speaker,
    pub text: String,
    pub confidence: f32,
    pub turn_id: u64,
    pub detected_at_ms: u64,
    pub context: Vec<ConversationTurn>,
}

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UnderstandingSnapshot {
    pub active: bool,
    pub turns: VecDeque<ConversationTurn>,
    pub events: VecDeque<MeaningfulEvent>,
    pub trimmed_turns: u64,
}

pub struct Detection {
    pub event_type: EventType,
    pub text: String,
    pub confidence: f32,
}

/// A local rule provider today. Future providers receive coherent turns/context,
/// rather than being called for each ASR fragment. No model client is implemented.
pub trait UnderstandingProvider {
    fn analyze(&self, turn: &ConversationTurn, context: &[ConversationTurn]) -> Option<Detection>;
}
