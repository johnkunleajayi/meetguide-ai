use serde::Serialize;
use std::collections::VecDeque;

#[derive(Clone, Copy, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Source {
    System,
    Microphone,
}
impl Source {
    pub fn wire(self) -> &'static str {
        match self {
            Self::System => "system",
            Self::Microphone => "microphone",
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Entry {
    pub id: u64,
    pub source: Source,
    pub text: String,
    pub final_text: bool,
    pub interrupted: bool,
    pub offset_ms: u64,
    #[serde(skip)]
    epoch: u64,
    #[serde(skip)]
    segment: u64,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StreamState {
    pub source: Source,
    pub state: String,
    pub message: Option<String>,
    pub dropped_chunks: u64,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub version: u64,
    pub session_id: u64,
    pub entries: VecDeque<Entry>,
    pub streams: Vec<StreamState>,
    pub trimmed: u64,
}

pub struct TranscriptStore {
    pub snapshot: Snapshot,
    next_id: u64,
}
impl Default for TranscriptStore {
    fn default() -> Self {
        Self {
            snapshot: Snapshot {
                version: 1,
                session_id: 0,
                entries: VecDeque::new(),
                streams: Vec::new(),
                trimmed: 0,
            },
            next_id: 0,
        }
    }
}
impl TranscriptStore {
    pub fn reset(&mut self, sources: &[Source]) {
        self.snapshot.version += 1;
        self.snapshot.session_id += 1;
        self.snapshot.entries.clear();
        self.snapshot.trimmed = 0;
        self.snapshot.streams = sources
            .iter()
            .map(|source| StreamState {
                source: *source,
                state: "connecting".into(),
                message: None,
                dropped_chunks: 0,
            })
            .collect();
    }
    pub fn state(&mut self, source: Source, state: &str, message: Option<&str>, dropped: u64) {
        if let Some(stream) = self
            .snapshot
            .streams
            .iter_mut()
            .find(|stream| stream.source == source)
        {
            stream.state = state.into();
            stream.message = message.map(str::to_owned);
            stream.dropped_chunks = dropped;
            self.snapshot.version += 1;
        }
        if matches!(state, "reconnecting" | "error" | "stopped") {
            for entry in self
                .snapshot
                .entries
                .iter_mut()
                .filter(|entry| entry.source == source && !entry.final_text)
            {
                entry.interrupted = true;
            }
        }
    }
    pub fn event(
        &mut self,
        source: Source,
        epoch: u64,
        segment: u64,
        offset_ms: u64,
        text: &str,
        final_text: bool,
    ) {
        if text.len() > 16384 {
            return;
        }
        let text: String = text.chars().take(4096).collect();
        if let Some(entry) = self.snapshot.entries.iter_mut().find(|entry| {
            entry.source == source && entry.epoch == epoch && entry.segment == segment
        }) {
            if entry.final_text {
                return;
            }
            entry.text = text;
            entry.final_text = final_text;
        } else if !text.is_empty() {
            self.next_id += 1;
            let entry = Entry {
                id: self.next_id,
                source,
                epoch,
                segment,
                offset_ms,
                text,
                final_text,
                interrupted: false,
            };
            let index = self
                .snapshot
                .entries
                .iter()
                .position(|old| old.offset_ms > offset_ms)
                .unwrap_or(self.snapshot.entries.len());
            self.snapshot.entries.insert(index, entry);
        }
        self.snapshot.entries.retain(|entry| !entry.text.is_empty());
        while self.snapshot.entries.len() > 200
            || self
                .snapshot
                .entries
                .iter()
                .map(|entry| entry.text.len())
                .sum::<usize>()
                > 65536
        {
            self.snapshot.entries.pop_front();
            self.snapshot.trimmed += 1;
        }
        self.snapshot.version += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn partials_replace_and_final_text_does_not_regress_or_duplicate() {
        let mut store = TranscriptStore::default();
        store.event(Source::System, 1, 0, 10, "Hello", false);
        store.event(Source::System, 1, 0, 10, "Hello there.", true);
        store.event(Source::System, 1, 0, 10, "Hello", false);
        assert_eq!(store.snapshot.entries.len(), 1);
        assert!(
            store.snapshot.entries[0].final_text
                && store.snapshot.entries[0].text == "Hello there."
        );
    }
    #[test]
    fn sources_and_reconnected_epochs_are_distinct_and_session_reset_clears_text() {
        let mut store = TranscriptStore::default();
        store.reset(&[Source::System, Source::Microphone]);
        for (source, epoch) in [
            (Source::System, 1),
            (Source::Microphone, 1),
            (Source::System, 2),
        ] {
            store.event(source, epoch, 0, epoch, "test", false);
        }
        assert_eq!(store.snapshot.entries.len(), 3);
        store.state(Source::System, "reconnecting", None, 1);
        assert!(store.snapshot.entries[0].interrupted);
        store.reset(&[]);
        assert!(store.snapshot.entries.is_empty());
    }
    #[test]
    fn long_meetings_have_bounded_memory_and_keep_recent_entries() {
        let mut store = TranscriptStore::default();
        for segment in 0..1000 {
            store.event(Source::System, 1, segment, segment, "test", true);
        }
        assert_eq!(store.snapshot.entries.len(), 200);
        assert_eq!(store.snapshot.trimmed, 800);
    }
}
