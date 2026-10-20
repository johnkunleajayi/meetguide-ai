//! Incremental bounded NDJSON framing, independent of HTTP packet/UTF-8 boundaries.
use serde::Deserialize;
#[derive(Deserialize)]
pub struct Event {
    pub question_id: String,
    pub attempt: u64,
    #[serde(flatten)]
    pub value: Value,
}
#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Value {
    Partial {
        answer: String,
    },
    Reset,
    Ready {
        result: super::transport::CueReply,
        backend_processing_ms: f64,
    },
    Error,
}
#[derive(Default)]
pub struct Decoder {
    buffer: Vec<u8>,
    received: usize,
}
impl Decoder {
    pub fn push(&mut self, bytes: &[u8]) -> Result<Vec<Event>, &'static str> {
        self.received += bytes.len();
        if self.received > 262144 {
            return Err("Invalid Live Cue stream. Please retry.");
        }
        self.buffer.extend_from_slice(bytes);
        let mut result = vec![];
        while let Some(end) = self.buffer.iter().position(|b| *b == b'\n') {
            if end > 32768 {
                return Err("Invalid Live Cue stream. Please retry.");
            }
            let line: Vec<u8> = self.buffer.drain(..=end).collect();
            result.push(
                serde_json::from_slice(&line)
                    .map_err(|_| "Invalid Live Cue stream. Please retry.")?,
            );
        }
        if self.buffer.len() > 32768 {
            return Err("Invalid Live Cue stream. Please retry.");
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn packet_and_unicode_boundaries_do_not_leak_json_fragments() {
        let bytes="{\"question_id\":\"q-test\",\"attempt\":2,\"type\":\"partial\",\"answer\":\"I would clarify café goals.\"}\n".as_bytes();
        let mut decoder = Decoder::default();
        let mut events = vec![];
        for byte in bytes {
            events.extend(decoder.push(&[*byte]).unwrap());
        }
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].question_id, "q-test");
        assert_eq!(events[0].attempt, 2);
        assert!(
            matches!(&events[0].value,Value::Partial {answer} if answer=="I would clarify café goals.")
        );
    }
    #[test]
    fn malformed_or_unbounded_frames_fail_closed() {
        assert!(Decoder::default().push(b"private-invalid-json\n").is_err());
        assert!(Decoder::default().push(&vec![b'x'; 32769]).is_err());
    }
}
