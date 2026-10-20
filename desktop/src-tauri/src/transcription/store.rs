use crate::understanding::{Speaker, UnderstandingEngine, UnderstandingSnapshot};
use serde::Serialize;
use std::collections::VecDeque;
use std::time::Instant;

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
    pub understanding: UnderstandingSnapshot,
}

pub struct TranscriptStore {
    pub snapshot: Snapshot,
    next_id: u64,
    understanding: UnderstandingEngine,
    clock: Instant,
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
                understanding: UnderstandingSnapshot::default(),
            },
            next_id: 0,
            understanding: UnderstandingEngine::default(),
            clock: Instant::now(),
        }
    }
}
impl TranscriptStore {
    pub fn reset(&mut self, sources: &[Source]) {
        self.understanding.reset(!sources.is_empty());
        self.clock = Instant::now();
        self.snapshot.understanding = self.understanding.snapshot.clone();
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
    pub fn tick_understanding(&mut self) {
        if self
            .understanding
            .tick(self.clock.elapsed().as_millis() as u64)
        {
            self.snapshot.understanding = self.understanding.snapshot.clone();
            self.snapshot.version += 1;
        }
    }
    pub fn take_candidates(&mut self) -> Vec<crate::understanding::candidate::Candidate> {
        self.understanding.take_candidates()
    }
    pub fn stop_understanding(&mut self) {
        self.understanding.stop();
        self.snapshot.understanding = self.understanding.snapshot.clone();
        self.snapshot.version += 1;
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
            self.understanding.gap(speaker(source));
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
        // A late interim/duplicate for an immutable final must not block understanding.
        if self.snapshot.entries.iter().any(|entry| {
            entry.source == source
                && entry.epoch == epoch
                && entry.segment == segment
                && entry.final_text
        }) {
            return;
        }
        let now = self.clock.elapsed().as_millis() as u64;
        if final_text {
            self.understanding
                .finalized(speaker(source), epoch, segment, text, offset_ms, now);
        } else {
            self.understanding.interim(speaker(source), text, now);
        }
        self.snapshot.understanding = self.understanding.snapshot.clone();
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

fn speaker(source: Source) -> Speaker {
    match source {
        Source::System => Speaker::Them,
        Source::Microphone => Speaker::You,
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
    #[test]
    fn understanding_survives_late_interims_and_stops_before_final_flush() {
        let mut store = TranscriptStore::default();
        store.reset(&[Source::System]);
        store.event(Source::System, 1, 1, 0, "Tell me about yourself.", true);
        store.event(Source::System, 1, 1, 0, "Tell me", false);
        store.clock = Instant::now() - std::time::Duration::from_millis(1300);
        let version = store.snapshot.version;
        store.tick_understanding();
        assert!(store.snapshot.version > version);
        assert_eq!(store.snapshot.understanding.events.len(), 1);
        store.stop_understanding();
        store.event(
            Source::System,
            1,
            2,
            2000,
            "Why did you choose Salesforce?",
            true,
        );
        assert_eq!(store.snapshot.understanding.turns.len(), 1);
        assert!(!store.snapshot.understanding.active);
        store.reset(&[]);
        assert!(store.snapshot.understanding.turns.is_empty());
        assert!(store.snapshot.understanding.events.is_empty());
        store.reset(&[Source::System]);
        assert!(store.snapshot.understanding.active);
    }
}

#[cfg(test)]
mod spoken_turn_regression {
    use super::*;
    #[test]
    fn split_provider_finals_remain_separate_transcript_entries_but_one_request() {
        let mut store = TranscriptStore::default();
        store.reset(&[Source::System]);
        store.event(
            Source::System,
            1,
            0,
            0,
            "Tell me about a Salesforce integration you worked on.",
            true,
        );
        store.clock = Instant::now() - std::time::Duration::from_millis(600);
        store.event(
            Source::System,
            1,
            600,
            600,
            "And challenges you faced.",
            true,
        );
        store.clock = Instant::now() - std::time::Duration::from_millis(2000);
        store.tick_understanding();
        assert_eq!(store.snapshot.entries.len(), 2);
        assert_eq!(store.snapshot.understanding.turns.len(), 1);
        assert_eq!(store.snapshot.understanding.events.len(), 1);
        assert!(store.snapshot.understanding.events[0]
            .text
            .contains("on and challenges you faced"));
        let version = store.snapshot.version;
        store.tick_understanding();
        assert_eq!(store.snapshot.version, version);
    }
}
