use serde::{Deserialize, Serialize};
use std::time::Duration;
use zeroize::Zeroizing;

#[derive(Clone, Serialize)]
pub struct CueTurn {
    pub speaker: &'static str,
    pub text: String,
}
#[derive(Clone, Serialize)]
pub struct CueInput {
    #[serde(rename = "type")]
    pub event_type: &'static str,
    pub speaker: &'static str,
    pub finalized: bool,
    pub confidence: f32,
    pub question: String,
    pub context: Vec<CueTurn>,
}
#[derive(Deserialize)]
pub struct CueReply {
    pub answer: String,
    pub grounding: String,
    pub sources: Vec<serde_json::Value>,
}

pub async fn generate(input: CueInput) -> Result<CueReply, &'static str> {
    // Keyring and the existing blocking API client stay off the async runtime.
    let (url, token) = tauri::async_runtime::spawn_blocking(|| {
        let token = crate::vault::load()?.ok_or("Please sign in again to prepare an answer.")?;
        let url = crate::api::Api::new()?.cue_url();
        Ok::<_, &'static str>((url, token))
    })
    .await
    .map_err(|_| "Unable to access your MeetGuide session.")??;
    send(url, token, input).await
}

async fn send(
    url: String,
    token: Zeroizing<String>,
    input: CueInput,
) -> Result<CueReply, &'static str> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(35))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Unable to connect for Live Cue.")?;
    let mut response = client
        .post(url)
        .bearer_auth(token.as_str())
        .json(&input)
        .send()
        .await
        .map_err(|_| "Unable to prepare an answer. Please retry.")?;
    if !response.status().is_success() {
        return Err(match response.status().as_u16() {
            401 => "Your MeetGuide session expired. Please sign in again.",
            429 => "Live Cue is busy. Please retry shortly.",
            _ => "Unable to prepare a grounded answer. Check the backend configuration and retry.",
        });
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "Live Cue connection interrupted. Please retry.")?
    {
        if bytes.len() + chunk.len() > 16384 {
            return Err("Invalid Live Cue response. Please retry.");
        }
        bytes.extend_from_slice(&chunk);
    }
    let reply: CueReply =
        serde_json::from_slice(&bytes).map_err(|_| "Invalid Live Cue response. Please retry.")?;
    if reply.answer.is_empty()
        || reply.answer.chars().count() > 2400
        || !matches!(
            reply.grounding.as_str(),
            "document_supported" | "general_approach"
        )
        || reply.sources.len() > 3
    {
        return Err("Invalid Live Cue response. Please retry.");
    }
    Ok(reply)
}
