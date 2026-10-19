use keyring::{Entry, Error};
use zeroize::Zeroizing;

const SERVICE: &str = "com.meetguide.desktop";
const ACCOUNT: &str = "backend-session-v1";

fn entry() -> Result<Entry, &'static str> {
    if !cfg!(target_os = "windows") {
        return Err("Secure desktop credential storage currently supports Windows only.");
    }
    Entry::new(SERVICE, ACCOUNT).map_err(|_| "Windows credential storage is unavailable.")
}

pub fn load() -> Result<Option<Zeroizing<String>>, &'static str> {
    match entry()?.get_password() {
        Ok(value) => Ok(Some(Zeroizing::new(value))),
        Err(Error::NoEntry) => Ok(None),
        Err(_) => Err("Unable to read Windows credential storage. Please retry."),
    }
}

pub fn save(token: &str) -> Result<(), &'static str> {
    entry()?
        .set_password(token)
        .map_err(|_| "Unable to save the session securely.")
}

pub fn clear() -> Result<(), &'static str> {
    match entry()?.delete_credential() {
        Ok(()) | Err(Error::NoEntry) => Ok(()),
        Err(_) => {
            Err("Session revoked, but Windows credential cleanup failed. Please retry sign out.")
        }
    }
}

#[cfg(all(test, target_os = "windows"))]
mod tests {
    use super::*;
    #[test]
    fn windows_credential_manager_can_persist_and_remove_a_test_entry() {
        // Separate disposable credential; never read or overwrite a real MeetGuide session.
        let account = format!(
            "test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        let entry = Entry::new("com.meetguide.desktop.tests", &account).unwrap();
        entry
            .set_password("non-sensitive-storage-test")
            .expect("Windows credential write failed");
        let result = entry.get_password();
        entry
            .delete_credential()
            .expect("Windows test credential cleanup failed");
        assert_eq!(result.unwrap(), "non-sensitive-storage-test");
        assert!(matches!(entry.get_password(), Err(Error::NoEntry)));
    }
}
