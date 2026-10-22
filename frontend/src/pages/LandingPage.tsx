import { AudioLines, ArrowRight, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";
import { HeroScene } from "../components/landing/HeroScene";
import { ConversationOrbit } from "../components/landing/ConversationOrbit";
import { HowItWorks } from "../components/landing/HowItWorks";
import { CodeAssistDemo } from "../components/landing/CodeAssistDemo";
import { PrivateDisplayDemo } from "../components/landing/PrivateDisplayDemo";
import { UseCases } from "../components/landing/UseCases";
import { GetMeetGuide } from "../components/landing/primitives";
import { Reveal } from "../components/landing/motion";
const capabilities = ["Real-time transcription", "Question detection", "Live Cue", "Code Assist", "Conversation continuity", "Context grounding", "Private Display", "Light + Dark"];
export function LandingPage() {
  return <>
    <HeroScene /><ConversationOrbit /><HowItWorks /><CodeAssistDemo /><PrivateDisplayDemo /><UseCases />
    <section className="mg-trust mg-light" id="privacy" aria-labelledby="privacy-title"><div className="mg-container"><Reveal className="mg-section-heading"><div><p className="mg-eyebrow">USEFUL ASSISTANCE. CLEAR BOUNDARIES.</p><h2 id="privacy-title">Built for the moment.<br />With privacy in mind.</h2></div></Reveal><div className="mg-trust-grid">
      <Reveal><article><AudioLines size={22} /><h3>Session-only conversation</h3><p>Live transcripts, conversation context and cues stay in memory for the active session. MeetGuide does not save them as permanent meeting history.</p></article></Reveal>
      <Reveal><article><FileCheck2 size={22} /><h3>Selected context</h3><p>You choose which reusable documents belong to a preparation. Documents outside that selection aren't used for its answers.</p></article></Reveal>
      <Reveal><article><ShieldCheck size={22} /><h3>Private Display</h3><p>Keep your desktop assistant out of supported Windows capture paths while it stays visible to you.</p><a className="mg-link" href="#private-display">See the preview <ArrowRight size={14} /></a></article></Reveal>
    </div><p className="mg-provider-note"><LockKeyhole size={14} aria-hidden="true" /> Use MeetGuide only in conversations you are authorized to process. Transcription and AI providers process the audio and bounded context required for assistance.</p></div></section>
    <div className="mg-capability-strip" role="region" aria-label="MeetGuide capabilities"><div className="mg-capability-track">{[0, 1].map(copy => <ul key={copy} aria-hidden={copy === 1 || undefined}>{capabilities.map(label => <li key={label}><span aria-hidden="true">✦</span>{label}</li>)}</ul>)}</div></div>
    <section className="mg-closing mg-dark" aria-labelledby="closing-title"><div className="mg-container"><Reveal><AudioLines size={42} strokeWidth={1.5} aria-hidden="true" /><p className="mg-eyebrow">MEETGUIDE AI</p><h2 id="closing-title">Stay present in<br />the conversation.</h2><p>Let MeetGuide handle what comes next.</p><div className="mg-actions"><GetMeetGuide /><a className="mg-link" href="#how-it-works">See how it works <ArrowRight size={16} /></a></div><span>Your real-time AI meeting assistant.</span></Reveal></div></section>
  </>;
}
