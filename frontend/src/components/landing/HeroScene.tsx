import { AudioLines, ArrowDown, Check, CircleCheck, Mic, Sparkles } from "lucide-react";
import { GetMeetGuide, MiniBrand, Waveform } from "./primitives";
import { Photo } from "./Photo";
import { useDemoClock } from "./motion";

export const heroQuestion = "How would you bring a team together around a difficult decision?";
export const heroAnswer = "I'd start by making the decision and its trade-offs clear. Then I'd hear from the people closest to the work, agree what success looks like, and turn that shared understanding into a practical next step.";
export function HeroScene() {
  const { ref, tick } = useDemoClock(14000, 11800);
  const words = heroAnswer.split(" ");
  const question = heroQuestion.slice(0, Math.max(0, Math.floor((tick - 700) / 27)));
  const detected = tick >= 2800, preparing = tick >= 3600;
  const count = Math.max(0, Math.floor((tick - 4600) / 90));
  const ready = count >= words.length;
  return <section className="mg-hero" id="product" aria-labelledby="hero-title">
    <div className="mg-container">
      <div className="mg-hero-intro"><div><p className="mg-eyebrow">YOUR REAL-TIME AI MEETING ASSISTANT</p><h1 id="hero-title">Bring your best.<br /><em>To every conversation.</em></h1></div><div className="mg-hero-aside"><p>Go in prepared. Stay in the moment. Get private, context-aware guidance when it's your turn to respond.</p><div className="mg-actions"><GetMeetGuide /><a className="mg-link" href="#how-it-works">See it in action <ArrowDown size={16} /></a></div></div></div>
      <div className="mg-hero-scene" ref={ref} role="region" aria-label="Animated Live Cue demonstration">
        <Photo className="mg-hero-photo" name="01_hero_meeting.png" priority alt="Professional engaged in a video conversation at her laptop" />
        <div className="mg-scene-note"><span className="mg-live-dot">In conversation</span><strong>You stay with the people.<br />MeetGuide stays with the context.</strong></div>
        <div className="mg-hero-console" aria-hidden="true"><div className="mg-console-bar"><MiniBrand /><AudioLines size={17} /></div><div className="mg-listening"><Mic size={13} /><span>Listening</span><Waveform /></div>
          <div className="mg-transcript"><span className="mg-micro-label">THEM</span><p>{question || "Following the conversation…"}</p><span className="mg-detected" data-show={detected}><CircleCheck size={12} />Question understood</span></div>
          <div className="mg-live-answer" data-show={preparing}><div className="mg-answer-top"><span><Sparkles size={14} />Live Cue</span><span>{ready ? "Ready to speak" : count > 0 ? "Responding" : "Preparing…"}</span></div><p>{count > 0 ? words.slice(0, count).join(" ") : "Finding the words, with your context."}{count > 0 && !ready && <span className="mg-caret" />}</p><span className="mg-grounding" data-show={ready}><Check size={12} />Based on selected context</span></div>
        </div>
        <p className="mg-sr-only">Illustrative product demo. Them: {heroQuestion} Live Cue: {heroAnswer} Ready to speak. Based on selected context. You choose what to say. No live services are connected.</p><span className="mg-scene-caption">ILLUSTRATIVE PRODUCT DEMONSTRATION</span>
      </div>
      <div className="mg-hero-bottom"><span>Before the conversation. During the conversation. Always in your hands.</span><span>Prepare on the web <b>↗</b> Use live on Windows</span></div>
    </div>
  </section>;
}
