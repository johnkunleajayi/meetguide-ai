//! The HWND belongs to Tauri's top-level window, not its child WebView2 control.
use super::state::Affinity;
use ::windows::Win32::{
    Foundation::HWND,
    UI::WindowsAndMessaging::{
        GetWindowDisplayAffinity, SetWindowDisplayAffinity, WINDOW_DISPLAY_AFFINITY,
    },
};

pub(super) struct NativeAffinity<'a>(pub &'a tauri::Window);

impl Affinity for NativeAffinity<'_> {
    fn supported(&self) -> bool {
        true
    }
    fn read(&self) -> Result<u32, ()> {
        let handle = self.0.hwnd().map_err(|_| ())?;
        let mut value = 0;
        // The handle remains owned by this process/window throughout this synchronous call.
        unsafe { GetWindowDisplayAffinity(HWND(handle.0), &mut value) }.map_err(|_| ())?;
        Ok(value)
    }
    fn write(&self, value: u32) -> Result<(), ()> {
        let handle = self.0.hwnd().map_err(|_| ())?;
        unsafe { SetWindowDisplayAffinity(HWND(handle.0), WINDOW_DISPLAY_AFFINITY(value)) }
            .map_err(|_| ())
    }
}
