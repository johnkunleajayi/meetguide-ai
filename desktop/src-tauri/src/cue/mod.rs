mod intent;
mod state;
#[cfg(test)]
mod tests;
mod transport;
mod worker;
use crate::understanding::domain::{EventType, MeaningfulEvent, Speaker};
pub use state::CueService;
use std::sync::Arc;
use transport::{CueInput, CueTurn};
pub use worker::start;

fn input(event: &MeaningfulEvent) -> Option<CueInput> {
    if event.event_type != EventType::Question
        || event.speaker != Speaker::Them
        || event.confidence < 0.82
        || !event.confidence.is_finite()
        || event.text.chars().count() > 1600
    {
        return None;
    }
    let mut context = Vec::new();
    let mut budget = 4000;
    for turn in event.context.iter().rev().take(6) {
        let text: String = turn.text.chars().take(1000.min(budget)).collect();
        if text.trim().is_empty() {
            continue;
        }
        budget -= text.chars().count();
        context.push(CueTurn {
            speaker: if turn.speaker == Speaker::Them {
                "them"
            } else {
                "you"
            },
            text,
        });
        if budget == 0 {
            break;
        }
    }
    context.reverse();
    Some(CueInput {
        event_type: "question",
        speaker: "them",
        finalized: true,
        confidence: event.confidence,
        question: event.text.clone(),
        context,
    })
}

#[tauri::command]
pub fn cue_status(
    audio: tauri::State<'_, Arc<crate::audio::AudioService>>,
) -> Result<state::CueSnapshot, String> {
    audio.cues.snapshot().map_err(str::to_owned)
}
#[tauri::command]
pub fn cue_prepare(
    session_id: u64,
    event_id: u64,
    retry: bool,
    audio: tauri::State<'_, Arc<crate::audio::AudioService>>,
) -> Result<(), String> {
    if retry {
        audio
            .cues
            .retry(session_id, event_id)
            .map_err(str::to_owned)?;
    }
    Ok(())
}
#[tauri::command]
pub fn cue_clear(
    session_id: u64,
    event_id: u64,
    audio: tauri::State<'_, Arc<crate::audio::AudioService>>,
) -> Result<(), String> {
    audio
        .cues
        .remove(session_id, event_id)
        .map_err(str::to_owned)
}
