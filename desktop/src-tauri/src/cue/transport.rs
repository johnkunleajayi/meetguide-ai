use serde::{Deserialize, Serialize};
use std::time::Duration;
use zeroize::Zeroizing;

#[derive(Clone, Serialize)]
pub struct CueTurn {
    pub speaker: &'static str,
    pub text: String,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct CodingContext {
    pub problem: String,
    pub language: String,
    pub code: String,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct CodeAssist {
    pub language: String,
    pub approach: String,
    pub code: String,
    pub complexity: Option<String>,
    pub what_to_say: String,
}
impl CodeAssist {
    pub fn valid(&self) -> bool {
        self.language.chars().count() <= 40
            && self.approach.chars().count() <= 1600
            && self.code.chars().count() <= 8000
            && self.what_to_say.chars().count() <= 1800
            && self
                .complexity
                .as_ref()
                .is_none_or(|v| v.chars().count() <= 1000)
    }
}
#[derive(Clone, Serialize)]
pub struct CueInput {
    pub cue_kind: &'static str,
    pub coding_context: Option<CodingContext>,
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
    #[serde(default)]
    pub code_assist: Option<CodeAssist>,
    pub answer: String,
    pub grounding: String,
    pub sources: Vec<serde_json::Value>,
}

pub async fn generate(
    input: CueInput,
    question_id: &str,
    preparation_token: Option<&str>,
    attempt: u64,
    mut progress: impl FnMut(Option<&str>, Option<&CodeAssist>),
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
    mut progress: impl FnMut(Option<&str>, Option<&CodeAssist>),
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
                super::stream::Value::Partial {
                    answer,
                    code_assist,
                } => {
                    if (input.cue_kind == "code") != code_assist.is_some()
                        || answer.is_empty()
                        || answer.chars().count() > 2400
                        || code_assist.as_ref().is_some_and(|v| !v.valid())
                    {
                        return Err("Invalid Live Cue stream. Please retry.");
                    }
                    progress(Some(&answer), code_assist.as_ref());
                }
                super::stream::Value::Reset => progress(None, None),
                super::stream::Value::Error => {
                    return Err("Unable to prepare a grounded answer. Please retry.")
                }
                super::stream::Value::Ready {
                    mut result,
                    backend_processing_ms,
                } => {
                    if (input.cue_kind == "code") != result.code_assist.is_some()
                        || result.code_assist.as_ref().is_some_and(|v| {
                            v.code.trim().is_empty()
                                || v.language.trim().is_empty()
                                || v.what_to_say.trim().is_empty()
                                || !v.valid()
                        })
                        || result.answer.is_empty()
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
