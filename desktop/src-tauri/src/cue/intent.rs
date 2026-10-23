use super::transport::CueTurn;
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Serialize)]
pub struct IntentInput {
    #[serde(skip)]
    pub question_id: String,
    pub text: String,
    pub context: Vec<CueTurn>,
    pub previous_request: Option<String>,
    pub can_continue: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IntentResult {
    pub kind: String,
    pub normalized_request: String,
    pub confidence: f32,
}

pub async fn classify(input: IntentInput) -> Result<IntentResult, &'static str> {
    let (url, token) = tauri::async_runtime::spawn_blocking(|| {
        Ok::<_, &'static str>((
            crate::api::Api::new()?.intent_url(),
            crate::vault::load()?.ok_or("Sign in required")?,
        ))
    })
    .await
    .map_err(|_| "Intent unavailable")??;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Intent unavailable")?;
    let mut response = client
        .post(url)
        .bearer_auth(token.as_str())
        .header("X-MeetGuide-Question-Id", &input.question_id)
        .json(&input)
        .send()
        .await
        .map_err(|error| {
            if error.is_timeout() {
                "Intent timeout"
            } else {
                "Intent unavailable"
            }
        })?;
    if !response.status().is_success() {
        return Err(failure_category(
            response.status().as_u16(),
            response
                .headers()
                .get("X-MeetGuide-Intent-Failure")
                .and_then(|v| v.to_str().ok()),
        ));
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| "Intent unavailable")? {
        if bytes.len() + chunk.len() > 16384 {
            return Err("Intent unavailable");
        }
        bytes.extend_from_slice(&chunk);
    }
    let result: IntentResult = serde_json::from_slice(&bytes).map_err(|_| "Intent unavailable")?;
    if !result.confidence.is_finite()
        || !(0.0..=1.0).contains(&result.confidence)
        || result.normalized_request.chars().count() > 1600
        || !matches!(
            result.kind.as_str(),
            "ACTIONABLE_REQUEST" | "CONTINUATION" | "FOLLOW_UP" | "NOT_ACTIONABLE"
        )
        || result.kind != "NOT_ACTIONABLE" && result.normalized_request.trim().chars().count() < 4
    {
        return Err("Intent unavailable");
    }
    Ok(result)
}

// Only fixed categories cross the diagnostic boundary; provider bodies are ignored.
pub(super) fn failure_category(status: u16, reason: Option<&str>) -> &'static str {
    match (status, reason) {
        (429, _) | (_, Some("RESOURCE_EXHAUSTED")) => "Intent rate limited",
        (408 | 504, _) | (_, Some("TIMEOUT")) => "Intent timeout",
        _ => "Intent unavailable",
    }
}
