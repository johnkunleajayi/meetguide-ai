//! Narrow grammatical gate, not a catalogue of coding problems. No model calls.
#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Request {
    New,
    FollowUp,
}

pub fn classify(text: &str, previous: bool) -> Option<Request> {
    let words: Vec<String> = text
        .to_lowercase()
        .chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '#' {
                c
            } else {
                ' '
            }
        })
        .collect::<String>()
        .split_whitespace()
        .map(str::to_owned)
        .collect();
    let has = |word: &str| words.iter().any(|v| v == word);
    let lead = words.iter().take(3).any(|w| {
        matches!(
            w.as_str(),
            "write" | "create" | "implement" | "code" | "how" | "can" | "could" | "please"
        )
    });
    if !lead {
        return None;
    }
    let referent = has("that") || has("this") || has("it");
    let language = words.iter().any(|w| {
        matches!(
            w.as_str(),
            "python" | "javascript" | "typescript" | "java" | "apex" | "c#" | "golang" | "sql"
        )
    }) || (has("in") && has("go"));
    let operation = has("optimize") || has("optimise") || has("improve");
    if previous
        && ((operation && (has("solution") || has("code") || has("algorithm")))
            || (referent && has("without") && (has("space") || has("memory")))
            || (referent && language))
    {
        return Some(Request::FollowUp);
    }
    let construct = words
        .iter()
        .any(|w| matches!(w.as_str(), "write" | "create" | "implement" | "code"));
    let object = words.iter().any(|w| {
        matches!(
            w.as_str(),
            "function"
                | "method"
                | "class"
                | "trigger"
                | "query"
                | "algorithm"
                | "script"
                | "program"
        )
    });
    let algorithm = words.iter().any(|w| {
        matches!(
            w.as_str(),
            "reverse" | "sort" | "traverse" | "merge" | "search"
        )
    }) && words
        .iter()
        .any(|w| matches!(w.as_str(), "array" | "list" | "tree" | "graph"));
    if (construct && (object || language)) || algorithm {
        Some(Request::New)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn obvious_requests_use_a_small_grammar() {
        for text in [
            "Write a function that finds duplicates in an array.",
            "How would you reverse a linked list?",
            "Write an Apex trigger to prevent duplicate Contacts.",
            "Create a SQL query to find the second highest salary.",
            "Implement this in Python.",
        ] {
            assert_eq!(classify(text, false), Some(Request::New), "{text}");
        }
    }
    #[test]
    fn followups_require_a_coding_chain_and_specific_reference() {
        for text in [
            "Can you optimize that solution?",
            "Can you do it without extra space?",
            "Implement this in Python.",
        ] {
            assert_eq!(classify(text, true), Some(Request::FollowUp), "{text}");
        }
        for text in [
            "Tell me about yourself.",
            "Why?",
            "Can you explain that?",
            "Can you optimize our sales process?",
            "What was the result?",
            "Tell me about your Python experience.",
        ] {
            assert_eq!(classify(text, true), None, "{text}");
        }
        assert_eq!(classify("Can you optimize that solution?", false), None);
        assert_eq!(classify("Can you do it without extra space?", false), None);
    }
}
