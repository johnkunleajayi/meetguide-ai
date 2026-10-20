import { useEffect, useState } from "react";
import { AudioLines, Check, FileText, Pause, Play, RotateCcw } from "lucide-react";

const stages = ["Listening", "Understanding", "Finding relevant experience", "Preparing answer", "Ready to speak"];
export const sampleAnswer = [
  "I worked on connecting Salesforce to an external system through APIs. One challenge was that the two systems represented the same data differently, so I worked through the field mappings and checked how values moved between them.",
  "I tested those exchanges in a sandbox before moving further. That helped me catch mismatches early and work through them with the team, rather than carry those assumptions into the live integration.",
];

export function ProductDemo() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [stage, setStage] = useState(() => reduced ? 4 : 0);
  const [playing, setPlaying] = useState(!reduced);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => {
      setReduced(media.matches);
      if (media.matches) { setPlaying(false); setStage(4); }
    };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!playing || reduced || stage === 4) return;
    const timer = window.setTimeout(() => setStage((value) => Math.min(value + 1, 4)), stage === 0 ? 1200 : 1000);
    return () => window.clearTimeout(timer);
  }, [stage, playing, reduced]);

  return <><p className="demo-differentiator">Something you can actually say — not another list of coaching instructions.</p><div className="product-demo" id="demo" role="region" aria-label="Interactive MeetGuide demonstration">
    <div className="demo-topbar">
      <div className="demo-title"><AudioLines size={17} aria-hidden="true" /><span>MeetGuide <span className="demo-dim">/ Live conversation</span></span></div>
      <span className="demo-example">Interactive example</span>
    </div>
    <div className="demo-body">
      <div className="demo-conversation">
        <div className="demo-speaker"><span className="speaker-dot" />Them <span className="demo-wave" data-playing={playing && stage < 4 && !reduced} aria-hidden="true">{[1, 2, 3, 4, 5, 6, 7].map(i => <i key={i} style={{ animationDelay: `${i * 110}ms` }} />)}</span></div>
        <p className="demo-question">“Tell me about a Salesforce integration you worked on and the challenges you faced.”</p>
        <div className={`demo-evidence ${stage >= 2 ? "is-found" : ""}`}>
          <div><FileText size={15} aria-hidden="true" /><span>YOUR CONTEXT</span><span className="demo-evidence-match">{stage >= 2 ? "Relevant experience found" : "Résumé / CV"}</span></div>
          <p>Salesforce integrations · External APIs · Field mapping · Sandbox testing</p>
          <span className="demo-fiction">Fictional résumé excerpt</span>
        </div>
      </div>
      <div className="demo-answer" data-ready={stage === 4} aria-label="Example ready-to-speak answer">
        <div className="demo-answer-label"><span className="cue-symbol">↗</span>LIVE CUE <span>{stage === 4 ? "Ready to speak" : "Working with your context"}</span></div>
        <div className="demo-spoken" aria-hidden={stage !== 4}>{sampleAnswer.map(p => <p key={p}>{p}</p>)}</div>
        {stage !== 4 &&
          <div className="demo-preparing"><AudioLines size={28} strokeWidth={1.3} aria-hidden="true" /><p>{stages[stage]}{stage === 3 ? "…" : ""}</p><span>Your experience. In your own voice.</span><div className="demo-skeleton" aria-hidden="true"><i /><i /><i /></div></div>}
        <div className="demo-answer-footer"><span>{stage === 4 ? <Check size={13} aria-hidden="true" /> : <span className="tiny-dot" />} Based on the example résumé</span><span>Session only</span></div>
      </div>
    </div>
    <div className="demo-bottom">
      <ol className="demo-stages" aria-label="Demonstration progress">{stages.map((name, index) => <li key={name} className={stage >= index ? "is-reached" : ""} aria-current={stage === index ? "step" : undefined}><span>{stage > index ? <Check size={10} aria-hidden="true" /> : index + 1}</span><span>{name}</span></li>)}</ol>
      <div className="demo-controls">
        {reduced ? <button onClick={() => setStage(value => (value + 1) % 5)}>Next demo step</button> : stage < 4 ? <button onClick={() => setPlaying(value => !value)}>{playing ? <Pause size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}{playing ? "Pause demo" : "Resume demo"}</button> : null}
        <button onClick={() => { setStage(0); setPlaying(!reduced); }}><RotateCcw size={13} aria-hidden="true" />Replay demo</button>
      </div>
    </div>
    <p className="demo-disclosure">Illustrative example. Fictional experience. No microphone, transcription or AI service is connected.</p>
  </div></>;
}
