use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tauri::State;

#[derive(Clone, Deserialize, Serialize)]
pub struct Selection {
    pub document_id: String,
    pub context_role: String,
}
#[derive(Clone, Deserialize, Serialize)]
pub struct Preparation {
    pub id: String,
    pub purpose: String,
    pub objective: String,
    pub documents: Vec<Selection>,
    pub active: bool,
    pub updated_at: String,
}
#[derive(Deserialize)]
pub struct Frozen {
    pub preparation_token: String,
}

#[tauri::command]
pub async fn preparation_list() -> Result<Vec<Preparation>, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let token = crate::vault::load()?.ok_or("Sign in to load preparations.")?;
        crate::api::Api::new()?.preparations(token.as_str())
    })
    .await
    .map_err(|_| "Unable to load preparations.".to_owned())?
    .map_err(str::to_owned)
}
#[tauri::command]
pub async fn preparation_activate(
    id: String,
    audio: State<'_, Arc<crate::audio::AudioService>>,
) -> Result<(), String> {
    let status = audio.status().map_err(str::to_owned)?;
    if matches!(
        status.state,
        crate::audio::CaptureState::Listening | crate::audio::CaptureState::Starting
    ) {
        return Err("Stop the live session before changing preparation.".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let token = crate::vault::load()?.ok_or("Sign in to select a preparation.")?;
        crate::api::Api::new()?.activate_preparation(token.as_str(), &id)
    })
    .await
    .map_err(|_| "Unable to select preparation.".to_owned())?
    .map_err(str::to_owned)
}
