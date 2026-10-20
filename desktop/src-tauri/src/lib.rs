mod audio;
mod cue;
mod preparation;
mod timing;
mod transcription;
mod understanding;
use tauri::{Emitter, Manager};
mod api;
mod auth;
mod loopback;
mod vault;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(std::sync::Arc::new(auth::AuthService::default()))
        .manage(std::sync::Arc::new(audio::AudioService::default()))
        .setup(|app| {
            let handle = app.handle().clone();
            app.state::<std::sync::Arc<audio::AudioService>>()
                .cues
                .set_publisher(std::sync::Arc::new(move |snapshot| {
                    let _ = handle.emit_to("main", "meetguide-cue-update", snapshot);
                }));
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                let _ = window.state::<std::sync::Arc<audio::AudioService>>().stop();
            }
        })
        .invoke_handler(tauri::generate_handler![
            auth::auth_restore,
            auth::auth_login,
            auth::auth_logout,
            auth::auth_cancel,
            preparation::preparation_list,
            preparation::preparation_activate,
            audio::audio_devices,
            audio::audio_start,
            audio::audio_status,
            audio::audio_stop,
            cue::cue_prepare,
            cue::cue_status,
            cue::cue_clear,
            transcription::transcription_status
        ])
        .run(tauri::generate_context!())
        .expect("error while running MeetGuide AI");
}
