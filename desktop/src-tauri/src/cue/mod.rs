mod state;
#[cfg(test)]
mod tests;
mod transport;
use crate::understanding::domain::{EventType, MeaningfulEvent, Speaker};
pub use state::CueService;
use std::sync::Arc;
use transport::{CueInput, CueTurn};

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
    prepare(audio.inner().clone(), session_id, event_id, retry)
}

#[tauri::command]
pub fn cue_clear(
    session_id: u64,
    event_id: u64,
    audio: tauri::State<'_, Arc<crate::audio::AudioService>>,
) -> Result<(), String> {
    audio
        .cues
        .clear(session_id, event_id)
        .map_err(str::to_owned)
}

fn current(store: &crate::transcription::TranscriptStore, session: u64, event: u64) -> bool {
    store.snapshot.session_id == session
        && store.snapshot.understanding.active
        && store
            .snapshot
            .understanding
            .events
            .back()
            .is_some_and(|item| item.id == event)
}
fn prepare(
    audio: Arc<crate::audio::AudioService>,
    session: u64,
    event: u64,
    retry: bool,
) -> Result<(), String> {
    let payload = {
        let store = audio
            .transcript
            .lock()
            .map_err(|_| "Live Cue is unavailable.")?;
        if !current(&store, session, event) {
            return Ok(());
        }
        input(
            store
                .snapshot
                .understanding
                .events
                .back()
                .expect("current event"),
        )
        .ok_or("This question cannot be prepared. Wait for the next complete question.")?
    };
    let Some((sequence, cancelled)) = audio.cues.begin(session, event, retry) else {
        return Ok(());
    };
    tauri::async_runtime::spawn(async move {
        let Some(result) = audio
            .cues
            .run(sequence, cancelled, || transport::generate(payload))
            .await
        else {
            return;
        };
        if audio
            .transcript
            .lock()
            .map(|store| current(&store, session, event))
            .unwrap_or(false)
        {
            audio.cues.finish(sequence, result);
        }
    });
    Ok(())
}
