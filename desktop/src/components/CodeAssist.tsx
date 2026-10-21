import type { CodeAssist as CodeAssistValue } from "../lib/cue";

export function CodeAssist({ value }: { value: CodeAssistValue }) {
  return <div className="code-assist-content">
    <span className="code-language">{value.language || "Auto-detect"}</span>
    {value.approach && <section><h4>Approach</h4><p>{value.approach}</p></section>}
    {value.code && <section><h4>Code</h4><pre tabIndex={0} aria-label={`${value.language || "Generated"} code`}><code>{value.code}</code></pre></section>}
    {value.complexity && <section><h4>Complexity</h4><p>{value.complexity}</p></section>}
    {value.what_to_say && <section><h4>What to say</h4><p>{value.what_to_say}</p></section>}
  </div>;
}
