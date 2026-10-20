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
    #[serde(skip)]
    pub timing: crate::timing::TransportTiming,
    pub answer: String,
    pub grounding: String,
    pub sources: Vec<serde_json::Value>,
}

pub async fn generate(
    input: CueInput,
    question_id: &str,
    preparation_token: Option<&str>,
    attempt: u64,
    mut progress: impl FnMut(Option<&str>),
) -> Result<CueReply, &'static str> {
    // Keyring and the existing blocking API client stay off the async runtime.
    let (url, token) = tauri::async_runtime::spawn_blocking(|| {
        let token = crate::vault::load()?.ok_or("Please sign in again to prepare an answer.")?;
        let url = crate::api::Api::new()?.cue_url();
        Ok::<_, &'static str>((url, token))
    })
    .await
    .map_err(|_| "Unable to access your MeetGuide session.")??;
    send(
        url,
        token,
        input,
        question_id,
        preparation_token,
        attempt,
        &mut progress,
    )
    .await
}

async fn send(
    url: String,
    token: Zeroizing<String>,
    input: CueInput,
    question_id: &str,
    preparation_token: Option<&str>,
    attempt: u64,
    mut progress: impl FnMut(Option<&str>),
) -> Result<CueReply, &'static str> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(35))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "Unable to connect for Live Cue.")?;
    let mut body = serde_json::to_value(&input).map_err(|_| "Unable to prepare an answer.")?;
    if let Some(token) = preparation_token {
        body["preparation_token"] = token.into();
    }
    let started = std::time::Instant::now();
    let mut response = client
        .post(url)
        .bearer_auth(token.as_str())
        .header("X-MeetGuide-Question-Id", question_id)
        .header("X-MeetGuide-Attempt", attempt)
        .header("Accept", "application/x-ndjson")
        .json(&body)
        .send()
        .await
        .map_err(|error| {
            crate::timing::emit(serde_json::json!({"stage":"desktop_request_failed","question_id":question_id,"provider_error_type":if error.is_timeout() { "TIMEOUT" } else { "NETWORK_ERROR" },"desktop_request_ms":started.elapsed().as_secs_f64()*1000.0}));
            "Unable to prepare an answer. Please retry."
        })?;
    let response_at = crate::timing::unix_ms();
    let backend_ms = response
        .headers()
        .get("x-meetguide-backend-ms")
        .and_then(|h| h.to_str().ok())
        .and_then(|h| h.parse::<f64>().ok())
        .filter(|v| v.is_finite() && *v >= 0.0);
    crate::timing::emit(
        serde_json::json!({"stage":"backend_response_headers", "question_id":question_id,"http_status":response.status().as_u16(),"backend_processing_ms":backend_ms,"request_to_headers_ms":started.elapsed().as_secs_f64()*1000.0,"at_unix_ms":response_at}),
    );
    if !response.status().is_success() {
        return Err(match response.status().as_u16() {
            401 => "Your MeetGuide session expired. Please sign in again.",
            429 => "Live Cue is busy. Please retry shortly.",
            _ => "Unable to prepare a grounded answer. Check the backend configuration and retry.",
        });
    }
    let mut decoder = super::stream::Decoder::default();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "Live Cue connection interrupted. Please retry.")?
    {
        for event in decoder.push(&chunk)? {
            if event.question_id != question_id || event.attempt != attempt {
                return Err("Invalid Live Cue stream. Please retry.");
            }
            match event.value {
                super::stream::Value::Partial { answer } => {
                    if answer.is_empty() || answer.chars().count() > 2400 {
                        return Err("Invalid Live Cue stream. Please retry.");
                    }
                    progress(Some(&answer));
                }
                super::stream::Value::Reset => progress(None),
                super::stream::Value::Error => {
                    return Err("Unable to prepare a grounded answer. Please retry.")
                }
                super::stream::Value::Ready {
                    mut result,
                    backend_processing_ms,
                } => {
                    if result.answer.is_empty()
                        || result.answer.chars().count() > 2400
                        || !matches!(
                            result.grounding.as_str(),
                            "document_supported" | "general_approach"
                        )
                        || result.sources.len() > 3
                        || !backend_processing_ms.is_finite()
                        || backend_processing_ms < 0.0
                    {
                        return Err("Invalid Live Cue response. Please retry.");
                    }
                    let elapsed = started.elapsed().as_secs_f64() * 1000.0;
                    result.timing = crate::timing::TransportTiming {
                        backend_processing_ms: Some(backend_processing_ms),
                        desktop_request_ms: elapsed,
                        desktop_transport_and_processing_ms: Some(
                            (elapsed - backend_processing_ms).max(0.0),
                        ),
                        backend_response_received_at_unix_ms: crate::timing::unix_ms(),
                    };
                    return Ok(result);
                }
            }
        }
    }
    Err("Live Cue stream ended before validation. Please retry.")
}
