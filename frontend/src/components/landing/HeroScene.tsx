import { AudioLines, Check, CircleCheck, Mic, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { GetMeetGuide, MiniBrand, Waveform } from "./primitives";
import { Photo } from "./Photo";
import { useDemoClock } from "./motion";

export const heroQuestion = "How would you approach this challenge?";
export const heroAnswer = "I'd start by understanding the constraints and what a good outcome looks like. Then I'd break the challenge into smaller steps, test the highest-risk assumption first, and use what we learn to decide what comes next.";

export function HeroScene() {
  const { ref, tick } = useDemoClock(11500, 9800);
  const words = heroAnswer.split(" ");
  const question = heroQuestion.slice(0, Math.max(0, Math.floor((tick - 700) / 32)));
  const detected = tick >= 2400;
  const preparing = tick >= 3400;
  const count = Math.max(0, Math.floor((tick - 4500) / 75));
  const ready = count >= words.length;
  return <section className="mg-hero mg-dark" id="product" aria-labelledby="hero-title">
    <div className="mg-container mg-hero-grid">
      <div className="mg-hero-copy">
        <p className="mg-eyebrow">YOUR REAL-TIME AI MEETING ASSISTANT</p>
        <h1 id="hero-title">Be present in the <em>conversation.</em></h1>
        <p className="mg-hero-description">MeetGuide listens, understands what you're being asked, and privately prepares the answer you need — while the conversation is still happening.</p>
        <div className="mg-actions"><GetMeetGuide /><a className="mg-link" href="#how-it-works"><span className="mg-play" aria-hidden="true">▷</span> See it in action</a></div>
        <ul className="mg-signals"><li><ShieldCheck size={14} />Private by design</li><li><Zap size={14} />Real-time assistance</li><li><AudioLines size={14} />Built for important conversations</li></ul>
      </div>
      <div className="mg-hero-scene" ref={ref} role="region" aria-label="Animated Live Cue demonstration">
        <Photo className="mg-hero-photo" name="01_hero_meeting.png" priority alt="Professional speaking with a colleague on a laptop, wearing an earbud" />
        <span className="mg-call-label"><span /> In conversation</span>
        <div className="mg-hero-console" aria-hidden="true">
          <div className="mg-console-bar"><MiniBrand /><span className="mg-live-dot">Live</span></div>
          <div className="mg-listening"><Mic size={13} /><span>Listening</span><Waveform /></div>
          <div className="mg-transcript"><span className="mg-micro-label">THEM</span><p>{question || <span className="mg-placeholder">Following the conversation…</span>}</p><span className="mg-detected" data-show={detected}><CircleCheck size={12} />Question detected</span></div>
          <div className="mg-live-answer" data-show={preparing}>
            <div className="mg-answer-top"><span><Sparkles size={14} /> Live Cue</span><span>{ready ? "Ready to speak" : count > 0 ? "Responding" : "Preparing…"}</span></div>
            <p>{count > 0 ? words.slice(0, count).join(" ") : "Preparing your answer…"}{count > 0 && !ready && <span className="mg-caret" />}</p>
            <span className="mg-grounding" data-show={ready}><Check size={12} />Based on selected context</span>
          </div>
        </div>
        <p className="mg-sr-only">Illustrative product demo. Them: {heroQuestion} Live Cue: {heroAnswer} Ready to speak. Based on selected context. No live services are connected.</p>
        <span className="mg-scene-caption">PRODUCT DEMONSTRATION · ILLUSTRATIVE CONTENT</span>
      </div>
    </div>
    <div className="mg-container mg-hero-bottom"><span>More than notes. Something you can actually say.</span><a href="#how-it-works">Explore MeetGuide <span aria-hidden="true">↓</span></a></div>
  </section>;
}
