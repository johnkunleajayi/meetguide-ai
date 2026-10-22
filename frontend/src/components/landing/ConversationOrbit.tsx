import { AudioLines, BriefcaseBusiness, Braces, Code2, Handshake, MessagesSquare, Presentation, Users, Workflow } from "lucide-react";
import type { CSSProperties } from "react";
import { Reveal } from "./motion";

const satellites = [
  ["Job Interviews", BriefcaseBusiness], ["Python", Code2], ["Sales Meetings", Handshake],
  ["Internal Meetings", Workflow], ["Technical Interviews", Braces], ["JavaScript", Code2],
  ["Client Meetings", MessagesSquare], ["Presentations & Q&A", Presentation],
] as const;
export function ConversationOrbit() {
  return <section className="mg-orbit-section mg-light" aria-labelledby="orbit-title"><div className="mg-container mg-orbit-layout">
    <Reveal className="mg-section-copy"><p className="mg-eyebrow">A LITTLE SUPPORT. A LOT OF POSSIBILITIES.</p><h2 id="orbit-title">One assistant.<br />Many conversations.</h2><p>From interviews to client calls, MeetGuide brings useful guidance to the moment you're in.</p><a className="mg-link" href="#use-cases">Find your conversation <span aria-hidden="true">↗</span></a></Reveal>
    <div className="mg-orbit" role="group" aria-label="Conversations and languages supported by MeetGuide">
      <div className="mg-orbit-ring mg-ring-outer" /><div className="mg-orbit-ring mg-ring-inner" /><div className="mg-orbit-center"><AudioLines size={48} strokeWidth={1.7} /><span>MeetGuide</span></div>
      {satellites.map(([label, Icon], index) => <div className={`mg-orbital-path ${index < 4 ? "mg-orbit-outer" : "mg-orbit-inner"}`} key={label} style={{ "--orbit-delay": `${-((index % 4) * 13 + (index >= 4 ? 6.5 : 0))}s`, "--initial-angle": `${index % 4 * 90 + (index >= 4 ? 45 : 0)}deg` } as CSSProperties}><span className="mg-satellite"><Icon size={20} strokeWidth={1.6} aria-hidden="true" /><span>{label}</span></span></div>)}
    </div>
    <p className="mg-orbit-note"><Users size={15} aria-hidden="true" /> Different conversations. The same thoughtful assistant.</p>
  </div></section>;
}
