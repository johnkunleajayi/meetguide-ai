fn main() {
    println!("cargo:rerun-if-env-changed=MEETGUIDE_API_URL");
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "auth_restore",
            "auth_login",
            "auth_logout",
            "auth_cancel",
        ]),
    ))
    .expect("unable to build MeetGuide desktop");
}
