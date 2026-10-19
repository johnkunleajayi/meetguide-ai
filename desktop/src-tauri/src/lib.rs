mod api;
mod auth;
mod loopback;
mod vault;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(std::sync::Arc::new(auth::AuthService::default()))
        .invoke_handler(tauri::generate_handler![
            auth::auth_restore,
            auth::auth_login,
            auth::auth_logout,
            auth::auth_cancel
        ])
        .run(tauri::generate_context!())
        .expect("error while running MeetGuide AI");
}
