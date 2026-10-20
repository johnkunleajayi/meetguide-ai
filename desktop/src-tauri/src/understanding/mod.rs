mod detector;
pub mod domain;
#[cfg(test)]
mod tests;
use detector::{fingerprint, LocalQuestionDetector};
use domain::*;
pub use domain::{Speaker, UnderstandingSnapshot};
use std::collections::VecDeque;

pub const SETTLE_MS: u64 = 1200;
pub const MERGE_GAP_MS: u64 = 3000;
pub const COOLDOWN_MS: u64 = 6000;
pub const MAX_TURNS: usize = 32;
pub const MAX_CONTEXT_BYTES: usize = 24000;
const THRESHOLD: f32 = 0.82;
const MAX_TURN_BYTES: usize = 4000;

#[derive(Default)]
struct Progress {
    interim: bool,
    last_activity: u64,
    last_final: u64,
    last_text: String,
    force_new: bool,
}
struct Pending {
    turn_id: u64,
    revision: u64,
}

pub struct UnderstandingEngine<P: UnderstandingProvider = LocalQuestionDetector> {
    pub snapshot: UnderstandingSnapshot,
    provider: P,
    progress: [Progress; 2],
    seen: VecDeque<(Speaker, u64, u64)>,
    fingerprints: VecDeque<String>,
    pending: Option<Pending>,
    last_event: Option<u64>,
    next_turn: u64,
    next_event: u64,
}
impl Default for UnderstandingEngine {
    fn default() -> Self {
        Self::new(LocalQuestionDetector)
    }
}
impl<P: UnderstandingProvider> UnderstandingEngine<P> {
    pub fn new(provider: P) -> Self {
        Self {
            snapshot: UnderstandingSnapshot::default(),
            provider,
            progress: Default::default(),
            seen: VecDeque::new(),
            fingerprints: VecDeque::new(),
            pending: None,
            last_event: None,
            next_turn: 0,
            next_event: 0,
        }
    }
    pub fn reset(&mut self, active: bool) {
        self.snapshot = UnderstandingSnapshot {
            active,
            ..Default::default()
        };
        self.progress = Default::default();
        self.seen.clear();
        self.fingerprints.clear();
        self.pending = None;
        self.last_event = None;
        self.next_turn = 0;
        self.next_event = 0;
    }
    pub fn stop(&mut self) {
        self.snapshot.active = false;
        self.pending = None;
    }
    pub fn gap(&mut self, speaker: Speaker) {
        self.progress[speaker.index()] = Progress {
            force_new: true,
            ..Default::default()
        };
        if speaker == Speaker::Them {
            self.pending = None;
        }
    }
    pub fn interim(&mut self, speaker: Speaker, text: &str, now: u64) {
        if !self.snapshot.active {
            return;
        }
        let progress = &mut self.progress[speaker.index()];
        if !progress.interim && now.saturating_sub(progress.last_activity) > MERGE_GAP_MS {
            progress.force_new = true;
        }
        progress.interim = !text.trim().is_empty();
        if progress.interim {
            progress.last_activity = now;
        }
    }
    pub fn finalized(
        &mut self,
        speaker: Speaker,
        epoch: u64,
        segment: u64,
        text: &str,
        offset: u64,
        now: u64,
    ) {
        if !self.snapshot.active || self.seen.contains(&(speaker, epoch, segment)) {
            return;
        }
        self.seen.push_back((speaker, epoch, segment));
        if self.seen.len() > 512 {
            self.seen.pop_front();
        }
        let progress = &mut self.progress[speaker.index()];
        progress.interim = false;
        let text = text.trim();
        if text.is_empty() {
            return;
        }
        let normalized = fingerprint(text);
        if normalized == progress.last_text && now.saturating_sub(progress.last_final) < 10000 {
            return;
        }
        let continuous =
            now.saturating_sub(progress.last_activity) <= MERGE_GAP_MS && !progress.force_new;
        progress.force_new = false;
        progress.last_activity = now;
        progress.last_final = now;
        progress.last_text = normalized;
        let text = if text.len() > MAX_TURN_BYTES {
            truncate(text, MAX_TURN_BYTES - 3) + "…"
        } else {
            text.to_owned()
        };
        let merge = self.snapshot.turns.back().is_some_and(|turn| {
            turn.speaker == speaker
                && turn.epoch == epoch
                && continuous
                && turn.text.len() + text.len() + 1 <= MAX_TURN_BYTES
        });
        if merge {
            let turn = self.snapshot.turns.back_mut().expect("existing turn");
            turn.text.push(' ');
            turn.text.push_str(&text);
            turn.last_segment_at_ms = offset;
            turn.revision += 1;
        } else {
            self.next_turn += 1;
            self.snapshot.turns.push_back(ConversationTurn {
                id: self.next_turn,
                speaker,
                text,
                started_at_ms: offset,
                last_segment_at_ms: offset,
                epoch,
                revision: 1,
            });
        }
        if speaker == Speaker::Them {
            let turn = self.snapshot.turns.back().expect("accepted final turn");
            self.pending = Some(Pending {
                turn_id: turn.id,
                revision: turn.revision,
            });
        }
        while self.snapshot.turns.len() > MAX_TURNS
            || self
                .snapshot
                .turns
                .iter()
                .map(|turn| turn.text.len())
                .sum::<usize>()
                > MAX_CONTEXT_BYTES
        {
            self.snapshot.turns.pop_front();
            self.snapshot.trimmed_turns += 1;
        }
    }
    pub fn tick(&mut self, now: u64) -> bool {
        if !self.snapshot.active {
            return false;
        }
        let Some(pending) = self.pending.take() else {
            return false;
        };
        let progress = &self.progress[Speaker::Them.index()];
        if progress.interim || now.saturating_sub(progress.last_activity) < SETTLE_MS {
            self.pending = Some(pending);
            return false;
        }
        let Some(turn) = self
            .snapshot
            .turns
            .iter()
            .find(|turn| turn.id == pending.turn_id && turn.revision == pending.revision)
        else {
            return false;
        };
        let context = recent_context(&self.snapshot.turns);
        let Some(candidate) = self.provider.analyze(turn, &context) else {
            return false;
        };
        if candidate.event_type != EventType::Question
            || !candidate.confidence.is_finite()
            || candidate.confidence < THRESHOLD
            || turn.speaker != Speaker::Them
        {
            return false;
        }
        let mut key = fingerprint(&candidate.text);
        // A short follow-up can recur after a different answer, while repeated
        // ASR/question events against the same answer still share one key.
        if matches!(
            key.as_str(),
            "why"
                | "what happened next"
                | "request you explain that"
                | "how did you solve that"
                | "why is that"
        ) {
            if let Some(answer) = context
                .iter()
                .rev()
                .find(|item| item.speaker == Speaker::You)
            {
                key = format!("{key}:answer:{}", answer.id);
            }
        }
        if key.is_empty() || self.fingerprints.contains(&key) {
            return false;
        }
        if self
            .last_event
            .is_some_and(|last| now.saturating_sub(last) < COOLDOWN_MS)
        {
            // Debounce distinct questions rather than silently losing a follow-up.
            self.pending = Some(pending);
            return false;
        }
        self.progress[Speaker::Them.index()].force_new = true;
        self.fingerprints.push_back(key);
        if self.fingerprints.len() > 128 {
            self.fingerprints.pop_front();
        }
        self.last_event = Some(now);
        self.next_event += 1;
        self.snapshot.events.push_back(MeaningfulEvent {
            id: self.next_event,
            event_type: EventType::Question,
            speaker: Speaker::Them,
            text: candidate.text,
            confidence: candidate.confidence,
            turn_id: turn.id,
            detected_at_ms: now,
            context,
        });
        if self.snapshot.events.len() > 8 {
            self.snapshot.events.pop_front();
        }
        true
    }
}
fn truncate(text: &str, limit: usize) -> String {
    let mut end = text.len().min(limit);
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    text[..end].to_owned()
}
fn recent_context(turns: &VecDeque<ConversationTurn>) -> Vec<ConversationTurn> {
    let mut context = Vec::new();
    let mut bytes = 0;
    for turn in turns.iter().rev().take(8) {
        if bytes + turn.text.len() > 6000 {
            break;
        }
        bytes += turn.text.len();
        context.push(turn.clone());
    }
    context.reverse();
    context
}
