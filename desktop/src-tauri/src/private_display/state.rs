use serde::Serialize;

pub(super) const NONE: u32 = 0;
pub(super) const EXCLUDE: u32 = 0x11;

pub(super) trait Affinity {
    fn supported(&self) -> bool;
    fn read(&self) -> Result<u32, ()>;
    fn write(&self, value: u32) -> Result<(), ()>;
}

#[derive(Clone, Debug, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct DisplayStatus {
    pub state: &'static str,
    pub requested_enabled: bool,
    pub message: Option<&'static str>,
    pub revision: u64,
}

pub(super) struct Controller {
    requested: bool,
    revision: u64,
}

impl Default for Controller {
    fn default() -> Self {
        Self {
            requested: true,
            revision: 0,
        }
    }
}

impl Controller {
    pub(super) fn update(
        &mut self,
        platform: &impl Affinity,
        requested: Option<bool>,
        repair: bool,
    ) -> DisplayStatus {
        self.revision += 1;
        if let Some(value) = requested {
            self.requested = value;
        }
        let mut status = DisplayStatus {
            state: "unsupported",
            requested_enabled: self.requested,
            message: Some("Private Display is available on Windows only."),
            revision: self.revision,
        };
        if !platform.supported() {
            return status;
        }
        let desired = if self.requested { EXCLUDE } else { NONE };
        let mut actual = platform.read();
        let mut failed = false;
        if requested.is_some() || (repair && actual != Ok(desired)) {
            failed = platform.write(desired).is_err();
            // Even a successful Set call is never treated as verified state.
            actual = platform.read();
        }
        (status.state, status.message) = match actual {
            Ok(EXCLUDE) => ("on", None),
            Ok(NONE) => ("off", None),
            Ok(_) => ("limited", Some("Windows has not confirmed capture exclusion. Some captures may show a blank window instead.")),
            Err(()) => ("unknown", Some("Unable to verify Private Display. Do not rely on capture exclusion until its state is confirmed.")),
        };
        if failed {
            status.message = Some("Windows could not change Private Display. The status shown is the last read-back result. Check status or try again.");
        } else if actual.is_ok() && actual != Ok(desired) {
            status.message = Some("Windows has not applied the requested capture setting. Check status or try again before sharing.");
        }
        status
    }
}
