use crate::api::valid_token;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use subtle::ConstantTimeEq;
use url::Url;
use zeroize::Zeroizing;

pub fn wait_for_code(
    listener: TcpListener,
    state: &str,
    cancelled: &AtomicBool,
) -> Result<Zeroizing<String>, &'static str> {
    listener
        .set_nonblocking(true)
        .map_err(|_| "Unable to listen for sign-in.")?;
    let deadline = Instant::now() + Duration::from_secs(180);
    let port = listener
        .local_addr()
        .map_err(|_| "Unable to read sign-in port.")?
        .port();
    while Instant::now() < deadline {
        if cancelled.load(Ordering::SeqCst) {
            return Err("Sign-in cancelled.");
        }
        match listener.accept() {
            Ok((mut stream, peer)) => {
                if !peer.ip().is_loopback() {
                    continue;
                }
                let request = read_request(&mut stream);
                let code = request
                    .as_deref()
                    .and_then(|request| parse_callback(request, port, state));
                let ok = code.is_some();
                let body = if ok {
                    "MeetGuide sign-in received. You can close this tab and return to MeetGuide AI."
                } else {
                    "Invalid MeetGuide sign-in callback. Return to the app to try again."
                };
                let status = if ok { "200 OK" } else { "400 Bad Request" };
                let _ = write!(stream, "HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: default-src 'none'; frame-ancestors 'none'\r\nConnection: close\r\n\r\n{body}", body.len());
                if let Some(code) = code {
                    return Ok(Zeroizing::new(code));
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(100))
            }
            Err(_) => return Err("Unable to receive sign-in callback."),
        }
    }
    Err("Sign-in timed out. Please try again.")
}

fn read_request(stream: &mut TcpStream) -> Option<Zeroizing<String>> {
    stream.set_read_timeout(Some(Duration::from_secs(1))).ok()?;
    stream
        .set_write_timeout(Some(Duration::from_secs(1)))
        .ok()?;
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut data = Zeroizing::new(Vec::new());
    let mut buffer = [0u8; 1024];
    while data.len() < 8192 && Instant::now() < deadline {
        let count = stream.read(&mut buffer).ok()?;
        if count == 0 {
            return None;
        }
        data.extend_from_slice(&buffer[..count]);
        if data.windows(4).any(|part| part == b"\r\n\r\n") {
            return String::from_utf8(data.to_vec()).ok().map(Zeroizing::new);
        }
    }
    None
}

fn parse_callback(request: &str, port: u16, state: &str) -> Option<String> {
    let mut lines = request.split("\r\n");
    let mut first = lines.next()?.split_whitespace();
    if first.next()? != "GET" {
        return None;
    }
    let target = first.next()?;
    if !target.starts_with("/callback?") || first.next()? != "HTTP/1.1" || first.next().is_some() {
        return None;
    }
    let hosts: Vec<_> = lines
        .filter_map(|line| line.split_once(':'))
        .filter(|(key, _)| key.eq_ignore_ascii_case("host"))
        .collect();
    if hosts.len() != 1 || hosts[0].1.trim() != format!("127.0.0.1:{port}") {
        return None;
    }
    let url = Url::parse(&format!("http://127.0.0.1:{port}{target}")).ok()?;
    if url.path() != "/callback" || url.fragment().is_some() {
        return None;
    }
    let pairs: Vec<_> = url.query_pairs().collect();
    if pairs.len() != 2 {
        return None;
    }
    let states: Vec<_> = pairs.iter().filter(|(key, _)| key == "state").collect();
    let codes: Vec<_> = pairs.iter().filter(|(key, _)| key == "code").collect();
    if states.len() != 1
        || codes.len() != 1
        || !bool::from(states[0].1.as_bytes().ct_eq(state.as_bytes()))
    {
        return None;
    }
    let code = &codes[0].1;
    let parts: Vec<_> = code.split('.').collect();
    if parts.len() != 2 || !parts.iter().all(|part| valid_token(part)) {
        return None;
    }
    Some(code.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(state: &str, host: &str) -> String {
        format!(
            "GET /callback?code={}.{}&state={state} HTTP/1.1\r\nHost: {host}\r\n\r\n",
            "n".repeat(43),
            "c".repeat(43)
        )
    }
    #[test]
    fn callback_requires_state_and_exact_loopback_host() {
        let state = "s".repeat(43);
        assert!(parse_callback(&request(&state, "127.0.0.1:12345"), 12345, &state).is_some());
        assert!(parse_callback(&request("wrong", "127.0.0.1:12345"), 12345, &state).is_none());
        assert!(parse_callback(&request(&state, "evil.test:12345"), 12345, &state).is_none());
        assert!(parse_callback(&request(&state, "127.0.0.1:9999"), 12345, &state).is_none());
    }
    #[test]
    fn rejects_duplicate_parameters_methods_and_paths() {
        let state = "s".repeat(43);
        let good = request(&state, "127.0.0.1:12345");
        for invalid in [
            good.replace("GET", "POST"),
            good.replace("/callback?", "/other?"),
            good.replace(" HTTP/1.1", &format!("&state={state} HTTP/1.1")),
        ] {
            assert!(parse_callback(&invalid, 12345, &state).is_none());
        }
    }
    #[test]
    fn cancelled_listener_exits_without_callback() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        assert!(wait_for_code(listener, &"s".repeat(43), &AtomicBool::new(true)).is_err());
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;
    #[test]
    fn listener_ignores_wrong_state_then_accepts_a_valid_callback_without_echoing_code() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let address = listener.local_addr().unwrap();
        let state = "s".repeat(43);
        let code = format!("{}.{}", "n".repeat(43), "c".repeat(43));
        let expected = code.clone();
        let thread_state = state.clone();
        let worker = std::thread::spawn(move || {
            wait_for_code(listener, &thread_state, &AtomicBool::new(false))
        });
        for (sent_state, expected_status) in
            [("wrong", "400 Bad Request"), (state.as_str(), "200 OK")]
        {
            let mut stream = TcpStream::connect(address).unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            write!(
                stream,
                "GET /callback?code={code}&state={sent_state} HTTP/1.1\r\nHost: {address}\r\n\r\n"
            )
            .unwrap();
            let mut response = String::new();
            stream.read_to_string(&mut response).unwrap();
            assert!(response.contains(expected_status));
            assert!(!response.contains(&code));
        }
        let received = worker.join().unwrap().unwrap();
        assert!(*received == expected);
        assert!(TcpStream::connect(address).is_err());
    }
}
