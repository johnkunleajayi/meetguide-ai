mod assembly;
pub mod candidate;
mod detector;
pub mod domain;
#[cfg(test)]
mod spoken_turn_tests;
#[cfg(test)]
mod tests;
use detector::{fingerprint, LocalQuestionDetector};
use domain::*;
pub use domain::{Speaker, UnderstandingSnapshot};
use std::collections::VecDeque;

pub const SETTLE_MS: u64 = 1200;
pub const MERGE_GAP_MS: u64 = 3000;
pub const DUPLICATE_MS: u64 = 45000;
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
    final_at: std::time::Instant,
    segment: u64,
    epoch: u64,
    turn_id: u64,
    revision: u64,
}

pub struct UnderstandingEngine<P: UnderstandingProvider = LocalQuestionDetector> {
    pub snapshot: UnderstandingSnapshot,
    provider: P,
    progress: [Progress; 2],
    seen: VecDeque<(Speaker, u64, u64)>,
    fingerprints: VecDeque<(String, u64)>,
    pending: VecDeque<Pending>,
    offered: Option<(u64, u64)>,
    outbox: VecDeque<candidate::Candidate>,
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
            pending: VecDeque::new(),
            offered: None,
            outbox: VecDeque::new(),
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
        self.pending.clear();
        self.offered = None;
        self.outbox.clear();
        self.next_turn = 0;
        self.next_event = 0;
    }
    pub fn stop(&mut self) {
        self.snapshot.active = false;
        self.pending.clear();
        self.outbox.clear();
    }
    pub fn gap(&mut self, speaker: Speaker) {
        self.progress[speaker.index()] = Progress {
            force_new: true,
            ..Default::default()
        };
        if speaker == Speaker::Them {
            self.pending.clear();
        }
    }
    pub fn interim(&mut self, speaker: Speaker, text: &str, now: u64) {
        if !self.snapshot.active {
            return;
        }
        if speaker == Speaker::You && !text.trim().is_empty() {
            self.progress[Speaker::Them.index()].force_new = true;
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
        if normalized == progress.last_text
            && now.saturating_sub(progress.last_final) < 10000
            && self
                .snapshot
                .turns
                .back()
                .is_some_and(|turn| turn.speaker == speaker)
        {
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
                && (speaker == Speaker::You || assembly::merge_text(&turn.text, &text))
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
            self.pending.retain(|pending| pending.turn_id != turn.id);
            self.pending.push_back(Pending {
                final_at: std::time::Instant::now(),
                segment,
                epoch,
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
    pub fn take_candidates(&mut self) -> Vec<candidate::Candidate> {
        self.outbox.drain(..).collect()
    }
    pub fn tick(&mut self, now: u64) -> bool {
        let progress = &self.progress[Speaker::Them.index()];
        if !self.snapshot.active
            || progress.interim
            || now.saturating_sub(progress.last_activity) < SETTLE_MS
        {
            return false;
        }
        let count = self.pending.len();
        let mut changed = false;
        for _ in 0..count {
            changed |= self.process_pending(now);
        }
        changed
    }
    fn process_pending(&mut self, now: u64) -> bool {
        if !self.snapshot.active {
            return false;
        }
        let Some(pending) = self.pending.pop_front() else {
            return false;
        };
        let progress = &self.progress[Speaker::Them.index()];
        if progress.interim || now.saturating_sub(progress.last_activity) < SETTLE_MS {
            self.pending.push_front(pending);
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
        let earlier = self
            .snapshot
            .turns
            .iter()
            .filter(|item| item.id <= turn.id)
            .cloned()
            .collect();
        let context = recent_context(&earlier);
        let detection_started = std::time::Instant::now();
        let detection = self.provider.analyze(turn, &context);
        let local_detection_ms = detection_started.elapsed().as_secs_f64() * 1000.0;
        if self.offered != Some((turn.id, turn.revision)) && candidate::meaningful(turn) {
            self.offered = Some((turn.id, turn.revision));
            let timing = crate::timing::CandidateTiming {
                assembly_wait_ms: detection_started
                    .saturating_duration_since(pending.final_at)
                    .as_secs_f64()
                    * 1000.0,
                local_detection_ms,
                final_at: pending.final_at,
                ..Default::default()
            };
            crate::timing::emit(
                serde_json::json!({"stage":"assembly_candidate", "question_id":timing.question_id, "turn_id":turn.id, "revision":turn.revision, "epoch":pending.epoch,"segment":pending.segment,"assembly_wait_ms":timing.assembly_wait_ms,"local_detection_ms":local_detection_ms,"configured_debounce_ms":SETTLE_MS,"at_unix_ms":crate::timing::unix_ms()}),
            );
            self.outbox.push_back(candidate::Candidate {
                timing,
                turn_id: turn.id,
                revision: turn.revision,
                text: turn.text.clone(),
                context: context.clone(),
                local: detection
                    .as_ref()
                    .filter(|item| item.confidence >= THRESHOLD && item.confidence.is_finite())
                    .map(|item| item.text.clone()),
            });
        }
        let Some(candidate) = detection else {
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
                | "how"
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
        self.fingerprints
            .retain(|(_, at)| now.saturating_sub(*at) < DUPLICATE_MS);
        if key.is_empty() || self.fingerprints.iter().any(|(seen, _)| seen == &key) {
            return false;
        }
        let enrichment = self
            .snapshot
            .events
            .back()
            .is_some_and(|event| event.turn_id == turn.id);
        for alias in assembly::prefix_keys(&turn.text)
            .into_iter()
            .chain(std::iter::once(key))
        {
            if !self.fingerprints.iter().any(|(seen, _)| seen == &alias) {
                self.fingerprints.push_back((alias, now));
            }
            if self.fingerprints.len() > 128 {
                self.fingerprints.pop_front();
            }
        }
        self.next_event += 1;
        if enrichment {
            self.snapshot.events.pop_back();
        }
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
