use crate::{
    api::{Api, User},
    loopback, vault,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use rand::{rngs::OsRng, RngCore};
use sha2::{Digest, Sha256};
use std::{
    net::TcpListener,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};
use tauri::{Manager, State};
use zeroize::Zeroizing;

#[derive(Default)]
pub struct AuthService {
    operation: Mutex<()>,
    cancelled: AtomicBool,
}

fn random_secret() -> Zeroizing<String> {
    let mut bytes = Zeroizing::new([0u8; 32]);
    OsRng.fill_bytes(bytes.as_mut());
    Zeroizing::new(URL_SAFE_NO_PAD.encode(bytes.as_ref()))
}

impl AuthService {
    pub(crate) fn restore(&self) -> Result<Option<User>, &'static str> {
        let _guard = self
            .operation
            .lock()
            .map_err(|_| "Authentication is unavailable. Restart MeetGuide.")?;
        let Some(token) = vault::load()? else {
            return Ok(None);
        };
        let user = Api::new()?.me(&token)?;
        if user.is_none() {
            vault::clear()?;
        }
        Ok(user)
    }

    fn login(&self) -> Result<User, &'static str> {
        let _guard = self
            .operation
            .try_lock()
            .map_err(|_| "Another authentication operation is in progress.")?;
        if vault::load()?.is_some() {
            return Err("A saved session already exists. Please restart MeetGuide to check it.");
        }
        self.cancelled.store(false, Ordering::SeqCst);
        let api = Api::new()?;
        let listener = TcpListener::bind(("127.0.0.1", 0))
            .map_err(|_| "Unable to open the local sign-in listener.")?;
        let port = listener
            .local_addr()
            .map_err(|_| "Unable to read sign-in port.")?
            .port();
        let state = random_secret();
        let verifier = random_secret();
        let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
        let url = api.login_url(port, &state, &challenge);
        webbrowser::open(url.as_str()).map_err(|_| "Unable to open your system browser.")?;
        let code = loopback::wait_for_code(listener, &state, &self.cancelled)?;
        if self.cancelled.load(Ordering::SeqCst) {
            return Err("Sign-in cancelled.");
        }
        let token = api.exchange(&code, &verifier)?;
        let result = (|| {
            if self.cancelled.load(Ordering::SeqCst) {
                return Err("Sign-in cancelled.");
            }
            let user = api
                .me(&token)?
                .ok_or("The new session was rejected. Please try again.")?;
            if self.cancelled.load(Ordering::SeqCst) {
                return Err("Sign-in cancelled.");
            }
            vault::save(&token)?;
            Ok(user)
        })();
        if result.is_err() {
            // Best effort cleanup if the new credential cannot be securely retained.
            let _ = api.logout(&token);
        }
        result
    }

    fn logout(&self) -> Result<(), &'static str> {
        let _guard = self
            .operation
            .try_lock()
            .map_err(|_| "Another authentication operation is in progress.")?;
        if let Some(token) = vault::load()? {
            Api::new()?.logout(&token)?;
            vault::clear()?;
        }
        Ok(())
    }
}

#[tauri::command]
pub async fn auth_restore(service: State<'_, Arc<AuthService>>) -> Result<Option<User>, String> {
    let service = service.inner().clone();
    tauri::async_runtime::spawn_blocking(move || service.restore())
        .await
        .map_err(|_| "Authentication task failed. Please restart MeetGuide.".to_owned())?
        .map_err(str::to_owned)
}

#[tauri::command]
pub async fn auth_login(
    app: tauri::AppHandle,
    service: State<'_, Arc<AuthService>>,
) -> Result<User, String> {
    let service = service.inner().clone();
    let user = tauri::async_runtime::spawn_blocking(move || service.login())
        .await
        .map_err(|_| "Authentication task failed. Please restart MeetGuide.".to_owned())?
        .map_err(str::to_owned)?;
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    Ok(user)
}
#[tauri::command]
pub async fn auth_logout(
    service: State<'_, Arc<AuthService>>,
    audio: State<'_, Arc<crate::audio::AudioService>>,
) -> Result<(), String> {
    let service = service.inner().clone();
    let audio = audio.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        audio.stop_with(|| {
            audio.clear_transcript();
            service.logout()
        })
    })
    .await
    .map_err(|_| "Authentication task failed. Please restart MeetGuide.".to_owned())?
    .map_err(str::to_owned)
}

#[tauri::command]
pub fn auth_cancel(service: State<'_, Arc<AuthService>>) {
    service.cancelled.store(true, Ordering::SeqCst);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fresh_secrets_are_random_and_pkce_s256_matches_the_standard_vector() {
        let first = random_secret();
        assert!(crate::api::valid_token(&first));
        assert_ne!(*first, *random_secret());
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assert_eq!(
            URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes())),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
    }
}
