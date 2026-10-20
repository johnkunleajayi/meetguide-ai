fn main() {
    println!("cargo:rerun-if-env-changed=MEETGUIDE_API_URL");
    if std::env::var("PROFILE").as_deref() == Ok("release") {
        assert!(
            std::env::var("MEETGUIDE_API_URL").is_ok_and(|value| !value.trim().is_empty()),
            "Set MEETGUIDE_API_URL explicitly for release builds (HTTPS for distribution)."
        );
    }
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "auth_restore",
            "auth_login",
            "auth_logout",
            "auth_cancel",
            "preparation_list",
            "preparation_activate",
            "audio_devices",
            "audio_start",
            "audio_status",
            "audio_stop",
            "transcription_status",
            "cue_prepare",
            "cue_status",
            "cue_clear",
        ]),
    ))
    .expect("unable to build MeetGuide desktop");
}
