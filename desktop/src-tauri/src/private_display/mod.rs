//! Per-window capture exclusion only. Never owns audio, authentication or cue state.
mod state;
#[cfg(test)]
mod tests;
#[cfg(windows)]
mod windows;

#[cfg(not(windows))]
use state::Affinity;
use state::{Controller, DisplayStatus};
use std::sync::Mutex;
use tauri::{Emitter, Manager};

#[derive(Default)]
pub struct PrivateDisplay(Mutex<Controller>);

#[cfg(not(windows))]
struct NativeAffinity;
#[cfg(not(windows))]
impl Affinity for NativeAffinity {
    fn supported(&self) -> bool {
        false
    }
    fn read(&self) -> Result<u32, ()> {
        Err(())
    }
    fn write(&self, _: u32) -> Result<(), ()> {
        Err(())
    }
}

fn update(
    window: &tauri::Window,
    requested: Option<bool>,
    repair: bool,
) -> Result<DisplayStatus, String> {
    if window.label() != "main" {
        return Err("Private Display is available only for the MeetGuide main window.".into());
    }
    let service = window
        .try_state::<PrivateDisplay>()
        .ok_or_else(|| "Private Display is unavailable. Restart MeetGuide.".to_owned())?;
    let mut controller = service
        .0
        .lock()
        .map_err(|_| "Unable to check Private Display. Restart MeetGuide.".to_owned())?;
    #[cfg(windows)]
    let platform = windows::NativeAffinity(window);
    #[cfg(not(windows))]
    let platform = NativeAffinity;
    let status = controller.update(&platform, requested, repair);
    let _ = window.emit_to("main", "meetguide-private-display", &status);
    Ok(status)
}

pub fn reconcile(window: &tauri::Window) -> Result<DisplayStatus, String> {
    update(window, None, true)
}

#[tauri::command]
pub fn private_display_status(window: tauri::Window) -> Result<DisplayStatus, String> {
    update(&window, None, false)
}

#[tauri::command]
pub fn private_display_set(window: tauri::Window, enabled: bool) -> Result<DisplayStatus, String> {
    update(&window, Some(enabled), false)
}
