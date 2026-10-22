import { useState } from "react";
import { Braces, Check, CornerDownRight, Sparkles } from "lucide-react";
import { Photo } from "./Photo";
import { Reveal, useDemoClock } from "./motion";

export const codingQuestions = ["Write a function that finds duplicates in an array.", "Can you optimize that solution?", "Can you do it without extra space?", "Implement this in JavaScript."];
const examples = [
  { language: "Python", approach: "Track seen values in a set. Keep each duplicate only once.", code: `def find_duplicates(values):
    seen, duplicates = set(), set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return list(duplicates)`, complexity: "Expected O(n) time · O(n) extra space", say: "I scan the array once. A set gives me fast membership checks, and a second set prevents repeated results." },
  { language: "Python", approach: "Use one frequency map, emitting each duplicate only when its count reaches two.", code: `def find_duplicates(values):
    counts = {}
    result = []
    for value in values:
        counts[value] = counts.get(value, 0) + 1
        if counts[value] == 2:
            result.append(value)
    return result`, complexity: "Expected O(n) time · O(n) extra space", say: "The first solution is already linear on average. This variation avoids a second set and reports each duplicate once." },
  { language: "Python", approach: "For integers in 1…n, use signs to mark seen indices. Input is modified; each value must occur at most twice.", code: `def find_duplicates(values):
    result = []
    for i in range(len(values)):
        index = abs(values[i]) - 1
        if values[index] < 0:
            result.append(index + 1)
        else:
            values[index] = -values[index]
    return result`, complexity: "O(n) time · O(1) extra space, excluding output", say: "Without extra space, I need constraints. If values are in 1 to n and occur at most twice, I can mark positions in place. Otherwise I'd discuss sorting and its trade-offs." },
  { language: "JavaScript", approach: "Keep the same in-place approach and the same 1…n, at-most-twice constraints.", code: `function findDuplicates(values) {
  const result = [];
  for (const value of values) {
    const index = Math.abs(value) - 1;
    if (values[index] < 0) result.push(index + 1);
    else values[index] = -values[index];
  }
  return result;
}`, complexity: "O(n) time · O(1) extra space, excluding output", say: "This is the same solution in JavaScript. It modifies the input, so I'd confirm that's acceptable before using it." },
];
export function CodeAssistDemo() {
  const { ref, tick } = useDemoClock(22000, 20500);
  const [selected, setSelected] = useState<number | null>(null);
  const index = selected ?? (tick < 6000 ? 0 : tick < 11000 ? 1 : tick < 16500 ? 2 : 3);
  const example = examples[index];
  const local = selected === null ? tick - [0, 6000, 11000, 16500][index] : 4500;
  const preparing = local < 900;
  const code = example.code.slice(0, Math.max(0, Math.floor((local - 900) / 4)));
  return <section className="mg-code-section mg-dark" id="code-assist" aria-labelledby="code-title"><div className="mg-container mg-code-layout">
    <Reveal className="mg-code-story"><p className="mg-eyebrow">MEETGUIDE CODE ASSIST</p><h2 id="code-title">When the conversation turns technical,<br /><em>MeetGuide does too.</em></h2><p>A clear approach. Readable code. Complexity where it matters. And the words to explain your thinking.</p><div className="mg-code-photo"><Photo name="03_technical_interview.png" alt="Developer discussing a programming problem while wearing headphones" /><span><Braces size={15} /> Think it through. Talk it through.</span></div></Reveal>
    <div className="mg-code-demo" ref={ref} role="region" aria-label="Code Assist conversation demonstration">
      <div className="mg-code-demo-top"><span><Braces size={17} />Code Assist</span><span className="mg-language">{example.language}</span></div>
      <div className="mg-code-question"><span className="mg-micro-label">THEM</span><p>{codingQuestions[index]}</p><span className="mg-detected" data-show="true"><Check size={12} />Question detected</span></div>
      <div className="mg-code-output" aria-hidden="true" key={index}>
        <div className="mg-code-state"><Sparkles size={13} />{preparing ? "Preparing" : local < 3000 ? "Responding" : "Ready"}<span>Illustrative example</span></div>
        <h3>Approach</h3><p>{example.approach}</p><h3>Code</h3><pre><code>{preparing ? "// Preparing solution…" : code}</code></pre><div className="mg-code-explanation"><div><h3>Complexity</h3><p>{example.complexity}</p></div><div><h3>What to say</h3><p>{example.say}</p></div></div>
      </div>
      <details className="mg-demo-details" onToggle={event => { if (event.currentTarget.open) setSelected(index); }}><summary>Read the complete code example</summary><p>{example.approach}</p><pre tabIndex={0}><code>{example.code}</code></pre><p>{example.complexity}</p><p>{example.say}</p></details>
      <div className="mg-code-continuity"><span><CornerDownRight size={14} /> Same conversation. Connected thinking.</span><div>{codingQuestions.map((question, i) => <button type="button" key={question} className={index === i ? "is-current" : ""} aria-pressed={index === i} onClick={() => setSelected(i)}>{question}</button>)}{selected !== null && <button type="button" onClick={() => setSelected(null)}>Play sequence</button>}</div></div>
    </div>
    <Reveal className="mg-followup-story"><h3>Follow-ups shouldn't require starting over.</h3><p>The active problem stays in context as you refine the solution, discuss constraints, or switch languages.</p><span>Original problem <b>→</b> Optimize it <b>→</b> Without extra space <b>→</b> JavaScript</span><small>Visual demonstration only. Generated code is never executed by MeetGuide.</small></Reveal>
  </div></section>;
}
