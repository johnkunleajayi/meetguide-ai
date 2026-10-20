use reqwest::blocking::Client;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use url::Url;
use zeroize::Zeroizing;

#[derive(Clone, Deserialize, Serialize)]
pub struct User {
    pub id: String,
    pub email: String,
    pub name: Option<String>,
    pub avatar_url: Option<String>,
}

#[derive(Deserialize)]
struct SessionGrant {
    session_token: String,
}

pub struct Api {
    base: Url,
    client: Client,
}

impl Api {
    pub fn new() -> Result<Self, &'static str> {
        let configured = option_env!("MEETGUIDE_API_URL")
            .or(if cfg!(debug_assertions) {
                Some("http://127.0.0.1:8000")
            } else {
                None
            })
            .ok_or("This build has no backend URL configured.")?;
        let base = Url::parse(configured).map_err(|_| "Invalid backend URL configuration.")?;
        if !valid_backend(&base) {
            return Err("Backend must use HTTPS, or HTTP on 127.0.0.1 for local development.");
        }
        let client = Client::builder()
            .timeout(Duration::from_secs(15))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| "Unable to initialize the backend connection.")?;
        Ok(Self { base, client })
    }

    pub fn cue_url(&self) -> String {
        self.endpoint("/api/cues/generate").to_string()
    }

    pub fn transcription_url(&self) -> String {
        let mut url = self.endpoint("/api/transcription/stream");
        let scheme = if url.scheme() == "https" { "wss" } else { "ws" };
        url.set_scheme(scheme).expect("validated backend scheme");
        url.to_string()
    }

    fn endpoint(&self, path: &str) -> Url {
        self.base.join(path).expect("fixed backend path")
    }

    pub fn login_url(&self, port: u16, state: &str, challenge: &str) -> Url {
        let mut url = self.endpoint("/api/auth/google/login");
        url.query_pairs_mut()
            .append_pair("desktop_port", &port.to_string())
            .append_pair("desktop_state", state)
            .append_pair("code_challenge", challenge);
        url
    }

    pub fn exchange(&self, code: &str, verifier: &str) -> Result<Zeroizing<String>, &'static str> {
        let response = self
            .client
            .post(self.endpoint("/api/auth/desktop/exchange"))
            .json(&serde_json::json!({ "code": code, "verifier": verifier }))
            .send()
            .map_err(|_| "Unable to reach MeetGuide. Please retry sign in.")?;
        if !response.status().is_success() {
            return Err("Desktop sign-in expired or was rejected. Please try again.");
        }
        let grant: SessionGrant = response
            .json()
            .map_err(|_| "Invalid authentication response.")?;
        if !valid_token(&grant.session_token) {
            return Err("Invalid authentication response.");
        }
        Ok(Zeroizing::new(grant.session_token))
    }

    pub fn me(&self, token: &str) -> Result<Option<User>, &'static str> {
        let response = self
            .client
            .get(self.endpoint("/api/auth/desktop/me"))
            .bearer_auth(token)
            .send()
            .map_err(|_| "Unable to reach MeetGuide. Please retry.")?;
        if response.status() == StatusCode::UNAUTHORIZED {
            return Ok(None);
        }
        if !response.status().is_success() {
            return Err("Unable to check your MeetGuide session. Please retry.");
        }
        response
            .json()
            .map(Some)
            .map_err(|_| "Invalid user response.")
    }

    pub fn logout(&self, token: &str) -> Result<(), &'static str> {
        let response = self
            .client
            .post(self.endpoint("/api/auth/desktop/logout"))
            .bearer_auth(token)
            .send()
            .map_err(|_| {
                "Unable to reach MeetGuide. Your session has not been signed out. Please retry."
            })?;
        if response.status().is_success() || response.status() == StatusCode::UNAUTHORIZED {
            Ok(())
        } else {
            Err("Unable to revoke your MeetGuide session. Please retry sign out.")
        }
    }
}

pub fn valid_token(value: &str) -> bool {
    value.len() == 43
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}

fn valid_backend(url: &Url) -> bool {
    (url.scheme() == "https" || (url.scheme() == "http" && url.host_str() == Some("127.0.0.1")))
        && url.host_str().is_some()
        && url.username().is_empty()
        && url.password().is_none()
        && url.path() == "/"
        && url.query().is_none()
        && url.fragment().is_none()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn backend_is_pinned_to_an_origin_and_secure_transport() {
        for value in ["https://api.example.test", "http://127.0.0.1:8000"] {
            assert!(valid_backend(&Url::parse(value).unwrap()));
        }
        for value in [
            "http://example.test",
            "https://user:secret@example.test",
            "https://api.example.test/path",
            "https://api.example.test/?token=value",
        ] {
            assert!(!valid_backend(&Url::parse(value).unwrap()));
        }
    }
    #[test]
    fn session_tokens_have_the_backend_opaque_format() {
        assert!(valid_token(&"a".repeat(43)));
        assert!(!valid_token(&"a".repeat(42)));
        assert!(!valid_token(&format!("{}.", "a".repeat(42))));
    }
}
