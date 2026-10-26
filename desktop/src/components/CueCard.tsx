import type { CueCard as Card } from "../lib/cue";
import { CodeAssist } from "./CodeAssist";
import { DesktopIcon } from "./DesktopIcon";
export function primaryCueId(cards: Card[]) {
  return cards.find(card => card.status === "generating" || card.status === "responding")?.id
    ?? cards.filter(card => card.status !== "queued").at(-1)?.id
    ?? cards[0]?.id;
}
export function CueCard({ card, current, removing, onRemove, onRetry }: { card: Card; current: boolean; removing: boolean; onRemove: () => void; onRetry: () => void }) {
  const status = card.status === "ready" ? (card.cueKind === "code" ? "Ready" : "Ready to speak") : card.status === "queued" ? "Queued" : card.status === "failed" ? "Answer unavailable" : card.status === "responding" ? "Responding" : "Preparing answer…";
  return <article className={`live-cue${card.cueKind === "code" ? " code-assist-card" : ""}`} data-current={current} data-status={card.status} aria-label={`Cue ${card.id}`}>
    <div className="cue-position-label">{current ? "CURRENT CUE" : card.status === "queued" ? "UP NEXT" : "EARLIER IN THIS SESSION"}<span>{card.cueKind === "code" ? <DesktopIcon name="code" size={14} /> : <DesktopIcon name="audio" size={14} />}</span></div>
    <div className="live-cue-heading"><h3>{card.cueKind === "code" ? "Code Assist" : "Question"}</h3><div className="live-cue-actions"><span className="cue-status">{card.status === "ready" && <DesktopIcon name="check" size={13} />}{(card.status === "generating" || card.status === "responding") && <i className="preparing-dot" aria-hidden="true" />}{status}</span>{card.answer && <button className="audio-refresh cue-remove" aria-label={`Remove cue ${card.id}`} disabled={removing} onClick={onRemove}>Remove</button>}</div></div>
    <p className="live-cue-question">{card.question}</p>
    {card.answer ? <>
      {card.status !== "ready" && <p className="cue-draft-note">Draft · final grounding checks pending</p>}
      {card.codeAssist ? <CodeAssist value={card.codeAssist} /> : <div className="live-cue-answer">{card.answer.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>}
      {card.status === "ready" && <p className="cue-grounding"><DesktopIcon name="document" size={13} />{card.grounding === "document_supported" ? `Uses ${card.sourceCount} document excerpt${card.sourceCount === 1 ? "" : "s"}` : "General approach · No personal experience claimed"}</p>}
    </> : card.status === "failed" ? <div className="cue-failure"><p role="alert">{card.error}</p><button className="retry-answer" onClick={onRetry}><DesktopIcon name="refresh" size={15} />Retry answer</button></div> : <p className="cue-waiting">{card.status === "queued" ? "Your question is waiting for the current answer." : "Preparing answer…"}</p>}
    {card.answer && card.status === "failed" && <div className="cue-failure"><p role="alert">{card.error}</p><button className="retry-answer" onClick={onRetry}><DesktopIcon name="refresh" size={15} />Retry answer</button></div>}
  </article>;
}
