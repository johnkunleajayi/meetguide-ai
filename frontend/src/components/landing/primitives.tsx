import { AudioLines, ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";

export function GetMeetGuide({ secondary = false }: { secondary?: boolean }) {
  return <Link className={`mg-button ${secondary ? "mg-button-outline" : ""}`} to="/app">Get MeetGuide <ArrowUpRight size={17} aria-hidden="true" /></Link>;
}
export function Waveform() {
  return <span className="mg-wave" aria-hidden="true">{Array.from({ length: 29 }, (_, i) =>
    <i key={i} style={{ height: `${5 + ((i * 17 + 7) % 25)}px`, animationDelay: `${i * -73}ms` }} />
  )}</span>;
}
export function MiniBrand() {
  return <span className="mg-mini-brand"><AudioLines size={19} aria-hidden="true" /> MeetGuide AI</span>;
}
