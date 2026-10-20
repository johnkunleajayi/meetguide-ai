import { AudioLines, MessageSquareText, Monitor, ScanText } from "lucide-react";

export function DesktopCompanion() {
  return <section className="ws-desktop" id="desktop-companion" aria-labelledby="desktop-title">
    <div className="ws-desktop-mark"><Monitor size={29} strokeWidth={1.3} aria-hidden="true" /><span>WINDOWS COMPANION</span></div>
    <div className="ws-desktop-copy"><p className="ws-eyebrow">FROM PREPARATION TO CONVERSATION</p><h2 id="desktop-title">Prepare here. Be present there.</h2><p>Use MeetGuide Desktop for live transcription and personalized Live Cues. Sign in with the same account to bring your context into the conversation.</p>
      <ul><li><AudioLines size={14} aria-hidden="true" />System & microphone audio</li><li><ScanText size={14} aria-hidden="true" />Live transcription</li><li><MessageSquareText size={14} aria-hidden="true" />Question detection & Live Cue</li></ul>
    </div>
  </section>;
}
