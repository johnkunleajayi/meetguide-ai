use super::state::{Affinity, Controller, EXCLUDE, NONE};
use std::cell::{Cell, RefCell};

struct Fake {
    value: Cell<Result<u32, ()>>,
    writes: RefCell<Vec<u32>>,
    fail: bool,
    ignore: bool,
    supported: bool,
}
impl Default for Fake {
    fn default() -> Self {
        Self {
            value: Cell::new(Ok(NONE)),
            writes: RefCell::new(vec![]),
            fail: false,
            ignore: false,
            supported: true,
        }
    }
}
impl Affinity for Fake {
    fn supported(&self) -> bool {
        self.supported
    }
    fn read(&self) -> Result<u32, ()> {
        self.value.get()
    }
    fn write(&self, value: u32) -> Result<(), ()> {
        self.writes.borrow_mut().push(value);
        if self.fail {
            return Err(());
        }
        if !self.ignore {
            self.value.set(Ok(value));
        }
        Ok(())
    }
}

#[test]
fn defaults_on_and_verifies_the_actual_affinity() {
    let mut controller = Controller::default();
    let platform = Fake::default();
    let status = controller.update(&platform, None, true);
    assert_eq!(*platform.writes.borrow(), [0x11]);
    assert_eq!(status.state, "on");
    assert!(status.requested_enabled && status.message.is_none());
}

#[test]
fn off_request_restores_none_and_survives_focus_reconciliation() {
    let mut controller = Controller::default();
    let platform = Fake::default();
    controller.update(&platform, Some(true), false);
    let off = controller.update(&platform, Some(false), false);
    assert_eq!(off.state, "off");
    assert!(!off.requested_enabled);
    assert_eq!(*platform.writes.borrow(), [EXCLUDE, NONE]);
    controller.update(&platform, None, true);
    assert_eq!(*platform.writes.borrow(), [EXCLUDE, NONE]);
}

#[test]
fn status_reads_without_optimistically_applying_the_default() {
    let mut controller = Controller::default();
    let platform = Fake::default();
    let status = controller.update(&platform, None, false);
    assert_eq!(status.state, "off");
    assert!(status.requested_enabled && platform.writes.borrow().is_empty());
}

#[test]
fn rejected_enable_and_disable_report_readback_instead_of_requested_state() {
    for (value, request, expected) in [(NONE, true, "off"), (EXCLUDE, false, "on")] {
        let mut controller = Controller::default();
        let platform = Fake {
            value: Cell::new(Ok(value)),
            fail: true,
            ..Default::default()
        };
        let status = controller.update(&platform, Some(request), false);
        assert_eq!(status.state, expected);
        assert!(status.message.unwrap().contains("could not change"));
    }
}

#[test]
fn success_without_matching_readback_is_not_on() {
    let mut controller = Controller::default();
    let platform = Fake {
        ignore: true,
        ..Default::default()
    };
    let status = controller.update(&platform, Some(true), false);
    assert_eq!(status.state, "off");
    assert!(status.message.is_some());
}

#[test]
fn unreadable_and_limited_states_are_not_reported_as_protected() {
    for (value, expected) in [(Err(()), "unknown"), (Ok(1), "limited")] {
        let mut controller = Controller::default();
        let platform = Fake {
            value: Cell::new(value),
            ignore: true,
            ..Default::default()
        };
        let status = controller.update(&platform, Some(true), false);
        assert_eq!(status.state, expected);
        assert!(status.message.is_some());
    }
}

#[test]
fn focus_repairs_a_lost_flag_and_revisions_order_ui_updates() {
    let mut controller = Controller::default();
    let platform = Fake::default();
    let first = controller.update(&platform, None, true);
    platform.value.set(Ok(NONE));
    let next = controller.update(&platform, None, true);
    assert_eq!(next.state, "on");
    assert!(next.revision > first.revision);
    assert_eq!(*platform.writes.borrow(), [EXCLUDE, EXCLUDE]);
}

#[test]
fn unsupported_platform_never_calls_affinity_apis() {
    let mut controller = Controller::default();
    let platform = Fake {
        supported: false,
        ..Default::default()
    };
    let status = controller.update(&platform, Some(true), false);
    assert_eq!(status.state, "unsupported");
    assert!(platform.writes.borrow().is_empty());
}
