//! Conservative English rules. Scores are heuristic strengths, not probabilities.
use super::domain::*;

#[derive(Default)]
pub struct LocalQuestionDetector;

pub(crate) fn words(text: &str) -> Vec<String> {
    text.to_lowercase()
        .chars()
        .filter(|c| !matches!(c, '\'' | '’'))
        .map(|c| if c.is_alphanumeric() { c } else { ' ' })
        .collect::<String>()
        .split_whitespace()
        .map(str::to_owned)
        .collect()
}

pub(crate) fn fingerprint(text: &str) -> String {
    let mut tokens = words(text);
    while tokens.first().is_some_and(|word| {
        matches!(
            word.as_str(),
            "um" | "uh" | "so" | "well" | "okay" | "please"
        )
    }) {
        tokens.remove(0);
    }
    if tokens.len() > 1
        && matches!(tokens[0].as_str(), "can" | "could" | "would")
        && tokens[1] == "you"
    {
        tokens[0] = "request".into();
    }
    tokens
        .into_iter()
        .filter(|word| !matches!(word.as_str(), "the" | "a" | "an" | "please"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn candidate(text: &str, has_context: bool) -> Option<Detection> {
    let text = text.trim();
    if text.ends_with("...") || text.ends_with('…') || text.ends_with([',', ':', ';', '-', '—'])
    {
        return None;
    }
    let mut tokens = words(text);
    while tokens.first().is_some_and(|word| {
        matches!(
            word.as_str(),
            "um" | "uh" | "so" | "well" | "okay" | "please"
        )
    }) {
        tokens.remove(0);
    }
    let tokens: Vec<&str> = tokens.iter().map(String::as_str).collect();
    let follow_up = has_context
        && (matches!(
            tokens.as_slice(),
            ["what", "happened", "next"]
                | ["can" | "could", "you", "explain", "that"]
                | ["how", "did", "you", "solve", "that"]
                | ["why", "is", "that"]
        ) || tokens.as_slice() == ["why"] && text.ends_with('?'));
    if follow_up {
        return Some(Detection {
            event_type: EventType::Question,
            text: text.to_owned(),
            confidence: 0.88,
        });
    }
    if tokens.len() < 3 {
        return None;
    }
    let first = tokens[0];
    let last = *tokens.last()?;
    let short_complete = matches!(
        tokens.as_slice(),
        ["who", "are", "you"]
            | ["are", "you", "ready"]
            | ["can" | "could", "you", "elaborate" | "clarify"]
    );
    if tokens.len() < 4 && !short_complete {
        return None;
    }
    if !short_complete
        && matches!(
            last,
            "the"
                | "a"
                | "an"
                | "and"
                | "or"
                | "but"
                | "to"
                | "of"
                | "with"
                | "for"
                | "about"
                | "on"
                | "in"
                | "at"
                | "from"
                | "that"
                | "which"
                | "when"
                | "why"
                | "how"
                | "what"
                | "your"
                | "my"
                | "our"
                | "their"
                | "is"
                | "are"
                | "was"
                | "were"
                | "be"
                | "been"
                | "being"
                | "have"
                | "has"
                | "had"
                | "can"
                | "could"
                | "would"
                | "should"
                | "will"
                | "do"
                | "did"
                | "does"
                | "you"
        )
    {
        return None;
    }
    let auxiliaries = [
        "am", "is", "are", "was", "were", "do", "does", "did", "can", "could", "would", "should",
        "will", "have", "has", "had", "couldnt", "wouldnt", "dont", "didnt", "isnt", "arent",
    ];
    let wh = matches!(
        first,
        "what" | "why" | "how" | "where" | "when" | "which" | "who"
    );
    // Reject embedded/reported clauses such as "How we handled it was...".
    let declarative_wh =
        wh && matches!(tokens[1], "i" | "we" | "you" | "they" | "he" | "she" | "it");
    let inverted = wh
        && !declarative_wh
        && tokens
            .iter()
            .skip(1)
            .take(4)
            .any(|word| auxiliaries.contains(word));
    let subject_question = wh
        && !declarative_wh
        && matches!(
            tokens[1],
            "happened" | "caused" | "changed" | "owns" | "leads" | "went" | "worked" | "matters"
        );
    let yes_no = auxiliaries.contains(&first)
        && matches!(
            tokens[1],
            "you" | "your" | "we" | "i" | "it" | "this" | "that" | "there" | "the" | "they"
        );
    let request = matches!(
        tokens.as_slice(),
        [
            "tell",
            "me",
            "about" | "how" | "why" | "what" | "whether" | "when" | "where",
            ..
        ] | ["walk", "me", "through", ..]
    ) || matches!(first, "explain" | "describe" | "outline" | "clarify")
        && tokens.len() >= 4;
    let confidence = if short_complete {
        0.88
    } else if inverted {
        0.94
    } else if request {
        0.92
    } else if yes_no {
        0.89
    } else if subject_question {
        0.86
    } else {
        return None;
    };
    Some(Detection {
        event_type: EventType::Question,
        text: text.to_owned(),
        confidence,
    })
}

impl UnderstandingProvider for LocalQuestionDetector {
    fn analyze(&self, turn: &ConversationTurn, context: &[ConversationTurn]) -> Option<Detection> {
        if turn.speaker != Speaker::Them
            || turn.text.trim_end().ends_with([',', ':', '-', '—'])
            || turn.text.trim_end().ends_with("...")
            || turn.text.trim_end().ends_with('…')
        {
            return None;
        }
        // A turn may include setup, a question, and several final ASR segments.
        // Evaluate sentences, not the provider's fragment boundaries.
        let has_context = context
            .iter()
            .any(|item| item.id != turn.id && words(&item.text).len() >= 4);
        turn.text
            .split_inclusive(['.', '?', '!', '\n'])
            .filter_map(|text| candidate(text, has_context))
            .last()
    }
}
