import { Eye, EyeOff, Monitor, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import { Reveal, useDemoClock } from "./motion";

function Screen({ shared, protectedView }: { shared?: boolean; protectedView: boolean }) {
  return <div className="mg-screen"><div className="mg-screen-chrome"><i /><i /><i /><span>Project discussion</span></div><div className="mg-screen-content"><div className="mg-slide"><span>QUARTERLY REVIEW</span><strong>A clear path<br />forward.</strong><div /><div /><div /></div><div className="mg-video-tiles"><span /><span /><span /></div><div className="mg-screen-assistant" aria-hidden={Boolean(shared && protectedView)} data-hidden={Boolean(shared && protectedView)}><Sparkles size={14} /><strong>MeetGuide</strong><p>I'd focus on the next milestone and the decisions we need to make together.</p></div></div><div className="mg-screen-base" /></div>;
}
export function PrivateDisplayDemo() {
  const { ref, tick } = useDemoClock(10000, 7000);
  const [manual, setManual] = useState<boolean | null>(null);
  const enabled = manual ?? tick >= 2400;
  return <section className="mg-private mg-light" id="private-display" aria-labelledby="private-title"><div className="mg-container">
    <Reveal className="mg-private-heading"><div><p className="mg-eyebrow">PRIVATE DISPLAY · WINDOWS</p><h2 id="private-title">Your assistant should<br />be for your eyes.</h2></div><p>MeetGuide can exclude its desktop window from supported Windows capture methods, helping keep your assistant private during supported screen-sharing workflows.</p></Reveal>
    <div ref={ref} className="mg-private-demo" role="region" aria-label="Private Display visual demonstration">
      <div><span className="mg-screen-label"><Eye size={14} /> YOUR SCREEN</span><Screen protectedView={enabled} /><p>MeetGuide stays visible to you.</p></div>
      <div className="mg-private-switch"><ShieldCheck size={25} /><span>Private Display</span><button type="button" role="switch" aria-checked={enabled} aria-label="Preview Private Display" onClick={() => setManual(!enabled)}><span>{enabled ? "ON" : "OFF"}</span><i /></button><small>Interactive preview</small><span className="mg-sharing-arrow" aria-hidden="true">→</span></div>
      <div><span className="mg-screen-label"><Monitor size={14} /> SHARED SCREEN</span><Screen shared protectedView={enabled} /><p>{enabled ? <><EyeOff size={13} />MeetGuide is excluded in this supported capture preview.</> : "Without protection, the assistant appears in this preview."}</p></div>
    </div>
    <p className="mg-private-disclosure">Illustration of supported Windows capture behavior. Protection varies by capture method; universal invisibility is not guaranteed. This preview does not change your device settings.</p>
  </div></section>;
}
