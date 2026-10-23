import { useState } from "react";
import { ArrowRight, Check, FileText, Link2, Sparkles } from "lucide-react";
import { MiniBrand, Waveform } from "./primitives";
import { Reveal, useDemoClock } from "./motion";
const stages = [
  { title: "Prepare", line: "Give the conversation a head start.", text: "Choose a purpose, set your objective, and select the documents that matter. Your preparation follows you to MeetGuide Desktop." },
  { title: "Listen", line: "Keep your attention on the room.", text: "With your permission, MeetGuide follows the conversation through your configured audio sources. You stay engaged with the people." },
  { title: "Understand", line: "A follow-up is still a conversation.", text: "Questions, requests and a simple “Why?” connect to what came before. You don't need to restate the whole discussion." },
  { title: "Retrieve", line: "The right context. For this moment.", text: "Only the documents selected for this preparation inform its answers. Yesterday's interview context stays out of today's client conversation." },
  { title: "Respond", line: "Something you can actually say.", text: "A natural, ready-to-speak cue takes shape privately. Keep useful cues in view, remove them when you're done, and decide what to say." },
];
export function PreparationJourney() {
  const { ref, tick } = useDemoClock(25000, 22000);
  const [selected, setSelected] = useState<number | null>(null);
  const index = selected ?? Math.min(4, Math.floor(tick / 5000));
  const stage = stages[index];
  return <section id="how-it-works" className="mg-journey" aria-labelledby="journey-title"><div className="mg-container">
    <Reveal className="mg-journey-heading"><p className="mg-eyebrow">A LITTLE PREPARATION. A DIFFERENT CONVERSATION.</p><h2 id="journey-title">Know your context.<br /><em>Find your next words.</em></h2></Reveal>
    <div className="mg-journey-tabs" role="tablist" aria-label="MeetGuide product journey">{stages.map((step, i) => <button key={step.title} type="button" role="tab" id={`journey-tab-${i}`} aria-selected={index === i} tabIndex={index === i ? 0 : -1} aria-controls="journey-panel" onClick={() => setSelected(i)} onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); const next = (i + (event.key === "ArrowRight" ? 1 : 4)) % 5; setSelected(next); document.getElementById(`journey-tab-${next}`)?.focus(); } }}><span>0{i + 1}</span>{step.title}<ArrowRight size={14} /></button>)}</div>
    <div ref={ref} id="journey-panel" role="tabpanel" aria-labelledby={`journey-tab-${index}`} className="mg-journey-panel"><div className="mg-journey-copy"><span className="mg-step-number">0{index + 1}</span><h3>{stage.line}</h3><p>{stage.text}</p>{selected !== null && <button className="mg-link" type="button" onClick={() => setSelected(null)}>Play the journey <ArrowRight size={14} /></button>}<small>Product illustration · no live services connected</small></div>
      <div className="mg-journey-visual" key={index}><div className="mg-illustration-top"><MiniBrand /><span>{stage.title}</span></div>
        {index === 0 && <div className="mg-preparation-preview"><span>CLIENT MEETING</span><h4>Agree the next project milestone.</h4><p>Selected for this conversation</p>{["Project Brief.pdf", "Meeting Notes.txt"].map(name => <div className="mg-doc-line" key={name}><FileText size={17} /><span>{name}</span><Check size={15} /></div>)}<div className="mg-illustration-foot"><Check size={14} />Prepared for Desktop</div></div>}
        {index === 1 && <div className="mg-listen-preview"><Waveform /><span>Following the conversation</span><blockquote>“What would you prioritize in the next phase?”</blockquote><div className="mg-illustration-foot"><Check size={14} />Question understood</div></div>}
        {index === 2 && <div className="mg-understand-preview"><p>“What would you prioritize in the next phase?”</p><div><Link2 size={18} /><span>“Why?”</span></div><p className="mg-resolved-request">The reason behind that recommendation.<small>Connected to the current discussion</small></p></div>}
        {index === 3 && <div className="mg-retrieve-preview"><span><FileText size={18} />Project Brief.pdf <Check size={14} /></span><blockquote>“The next phase focuses on a small pilot before a wider rollout.”</blockquote><div className="mg-context-connector"><i /><span>Selected context → relevant guidance</span><i /></div><p>Context chosen by you.<br />Brought forward when it matters.</p></div>}
        {index === 4 && <div className="mg-response-preview"><span className="mg-detected" data-show="true"><Sparkles size={14} />Ready to speak</span><blockquote>“I'd start with the pilot. It gives us a focused way to test the approach, hear from the people using it, and address the risks before a wider rollout.”</blockquote><div className="mg-illustration-foot"><Check size={14} />Based on selected context</div><p>You choose the words. MeetGuide helps you find them.</p></div>}
      </div>
    </div>
  </div></section>;
}
