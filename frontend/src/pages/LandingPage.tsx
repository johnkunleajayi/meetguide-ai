import { ArrowRight, AudioLines, FileCheck2, LockKeyhole, ShieldCheck } from "lucide-react";
import { HeroScene } from "../components/landing/HeroScene";
import { PreparationJourney } from "../components/landing/PreparationJourney";
import { CodeAssistDemo } from "../components/landing/CodeAssistDemo";
import { PrivateDisplayDemo } from "../components/landing/PrivateDisplayDemo";
import { UseCases } from "../components/landing/UseCases";
import { GetMeetGuide } from "../components/landing/primitives";
import { Reveal } from "../components/landing/motion";
export function LandingPage() {
  return <><HeroScene /><PreparationJourney /><UseCases /><CodeAssistDemo /><PrivateDisplayDemo />
    <section className="mg-trust" id="privacy" aria-labelledby="privacy-title"><div className="mg-container"><Reveal className="mg-trust-heading"><LockKeyhole size={24} /><h2 id="privacy-title">Useful in the moment.<br />Thoughtful about what stays.</h2></Reveal><div className="mg-trust-grid">
      <article><AudioLines size={22} /><h3>A session, not a permanent record.</h3><p>Live transcripts, conversation context and cues stay in memory for the active session. They aren't saved as permanent meeting history.</p></article>
      <article><FileCheck2 size={22} /><h3>Your context. Your selection.</h3><p>Reusable documents are private to your account. Only those you select belong to a preparation. Deleting a document removes its stored content.</p></article>
      <article><ShieldCheck size={22} /><h3>You stay in control.</h3><p>Use MeetGuide in conversations you are authorized to process. Audio and relevant context are processed by service providers to deliver assistance.</p></article>
    </div></div></section>
    <section className="mg-closing mg-dark" aria-labelledby="closing-title"><div className="mg-container"><Reveal><p className="mg-eyebrow">THE NEXT CONVERSATION IS YOURS.</p><h2 id="closing-title">Be ready for<br /><em>your moment.</em></h2><div className="mg-actions"><GetMeetGuide /><a className="mg-link" href="#how-it-works">Explore how it works <ArrowRight size={16} /></a></div><p>Your real-time AI meeting assistant.</p></Reveal></div></section>
  </>;
}
