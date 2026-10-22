import { Check, FileText, Sparkles } from "lucide-react";
import { Reveal, useDemoClock } from "./motion";
import { Waveform } from "./primitives";

export function HowItWorks() {
  const { ref, tick } = useDemoClock(10500, 9500);
  const answer = "I'd clarify the goal first, then work through the options and explain the trade-offs. That gives us a practical next step we can agree on.";
  const visible = answer.slice(0, Math.max(0, Math.floor((tick - 3600) / 25)));
  return <section className="mg-how mg-light" id="how-it-works" aria-labelledby="how-title"><div className="mg-container">
    <Reveal><p className="mg-eyebrow">A SIMPLE WAY TO STAY WITH THE MOMENT</p><h2 id="how-title">Prepare. Listen. Respond.</h2><p className="mg-section-intro">Your context before the call. The right support during it.</p></Reveal>
    <Reveal><div className="mg-steps" ref={ref}>
      <article><div className="mg-step-heading"><span>01</span><div><h3>Prepare</h3><p>Give MeetGuide the context that matters.</p></div></div><div className="mg-preparation-demo"><div className="mg-panel-label">Meeting preparation <span>Selected context</span></div>{["Resume.pdf", "Job Description.pdf", "Company Notes.pdf", "Product Brief.pdf"].map((name, i) => <div className="mg-doc-line" key={name} style={{ animationDelay: `${i * 140}ms` }}><FileText size={15} aria-hidden="true" /><span>{name}</span><Check size={13} aria-label="Selected" /></div>)}</div><p className="mg-step-note">Prepare on the web. Choose only what belongs in this session.</p></article>
      <span className="mg-connector" aria-hidden="true"><i /></span>
      <article><div className="mg-step-heading"><span>02</span><div><h3>Listen</h3><p>MeetGuide follows the conversation in real time.</p></div></div><div className="mg-listen-demo" aria-hidden="true"><div className="mg-demo-audio"><Waveform /><span>Listening</span></div><span className="mg-micro-label">THEM</span><p>“How would you approach this challenge?”</p><span className="mg-detected" data-show={tick >= 2200}><Check size={12} />Question detected</span></div><p className="mg-step-note">Use the Windows desktop companion during the conversation.</p></article>
      <span className="mg-connector" aria-hidden="true"><i /></span>
      <article><div className="mg-step-heading"><span>03</span><div><h3>Respond</h3><p>Get something useful before the moment passes.</p></div></div><div className="mg-respond-demo" aria-hidden="true"><div className="mg-panel-label"><Sparkles size={14} />Live Cue <span>{tick >= 8200 ? "Ready to speak" : "Preparing"}</span></div><p>{visible || "Preparing your answer…"}</p><span className="mg-grounding"><Check size={12} />Based on selected context</span></div><p className="mg-step-note">A natural response, not another list of coaching instructions.</p></article>
    </div></Reveal>
    <p className="mg-sr-only">Illustrative response: {answer}</p>
  </div></section>;
}
