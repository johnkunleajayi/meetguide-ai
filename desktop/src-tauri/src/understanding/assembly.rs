//! Small linguistic assembly rules. Never joins across speakers, gaps or epochs;
//! those boundaries are enforced by the engine before consulting these helpers.
use super::detector::{candidate, fingerprint, words};

fn connector(text: &str) -> bool {
    words(text).first().is_some_and(|word| {
        matches!(
            word.as_str(),
            "and"
                | "but"
                | "also"
                | "especially"
                | "or"
                | "for"
                | "with"
                | "in"
                | "on"
                | "about"
                | "including"
        )
    })
}

pub(super) fn request_lead(text: &str) -> bool {
    let tokens = words(text);
    matches!(
        tokens
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>()
            .as_slice(),
        [
            "tell",
            "me",
            "about" | "how" | "why" | "what" | "whether" | "when" | "where",
            ..
        ] | ["walk", "me", "through", ..]
            | ["describe" | "explain" | "outline" | "clarify", _, ..]
    ) || candidate(text, true).is_some()
}

fn sentences(text: &str) -> Vec<&str> {
    text.split_inclusive(['.', '?', '!', '\n'])
        .filter(|part| !part.trim().is_empty())
        .collect()
}

pub(super) fn linked_request(previous: &str, next: &str) -> bool {
    if !sentences(previous).iter().any(|part| request_lead(part)) {
        return false;
    }
    if connector(next) {
        return true;
    }
    // Nearby follow-on questions add detail; a fresh imperative starts a new request.
    let tokens = words(next);
    tokens.first().is_some_and(|word| {
        matches!(
            word.as_str(),
            "what" | "how" | "why" | "which" | "who" | "where" | "when" | "can" | "could" | "would"
        )
    }) && candidate(next, true).is_some()
}

pub(super) fn merge_text(previous: &str, next: &str) -> bool {
    (!previous.trim_end().ends_with(['.', '?', '!', '…']) && candidate(previous, true).is_none())
        || linked_request(previous, next)
}

fn join(parts: &[&str]) -> String {
    let mut result = String::new();
    for part in parts {
        let part = part.trim();
        if !result.is_empty() {
            if connector(part) {
                while result.ends_with(['.', '?', '!']) {
                    result.pop();
                }
            }
            result.push(' ');
        }
        if connector(part) {
            let mut chars = part.chars();
            if let Some(first) = chars.next() {
                result.extend(first.to_lowercase());
            }
            result.push_str(chars.as_str());
        } else {
            result.push_str(part);
        }
    }
    result
}

// Scenario framing is retained only when it contains a direct interrogative clause.
// A scenario statement alone (or reported "how we ...") is not actionable.
pub(super) fn scenario_detection(text: &str) -> Option<super::domain::Detection> {
    let tokens = words(text);
    if !tokens
        .first()
        .is_some_and(|w| matches!(w.as_str(), "suppose" | "imagine"))
    {
        return None;
    }
    tokens.windows(3).enumerate().find_map(|(i, w)| {
        (matches!(w[0].as_str(), "what" | "how" | "why" | "which")
            && matches!(w[1].as_str(), "would" | "will" | "could" | "should" | "do")
            && w[2] == "you")
            .then_some(())
            .and_then(|_| candidate(&tokens[i..].join(" "), true))
    })
}

// Keep the request and its qualifiers/questions, excluding preceding narrative setup.
pub(super) fn effective_request(text: &str) -> Option<String> {
    if scenario_detection(text).is_some() {
        return Some(text.trim().to_owned());
    }
    let parts = sentences(text);
    let start = parts.iter().position(|part| request_lead(part))?;
    Some(join(&parts[start..]))
}

// Also remember prefix forms so replay split differently does not emit extra cues.
pub(super) fn prefix_keys(text: &str) -> Vec<String> {
    let parts = sentences(text);
    let Some(start) = parts.iter().position(|part| request_lead(part)) else {
        return vec![];
    };
    (start..parts.len())
        .map(|end| fingerprint(&join(&parts[start..=end])))
        .collect()
}
