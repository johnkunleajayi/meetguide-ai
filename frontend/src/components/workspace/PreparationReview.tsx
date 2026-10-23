import { ArrowDownRight, ArrowUpRight, Check, FileCheck2, Monitor, ShieldCheck } from "lucide-react";
import { CODING_LANGUAGES, type PreparationInput } from "../../lib/preparations";
interface Props { draft: PreparationInput; purposeLabel: string; names: string[]; busy: boolean; disabled: boolean; saved: boolean; dirty: boolean; onSave: () => void }
export function PreparationReview({ draft, purposeLabel, names, busy, disabled, saved, dirty, onSave }: Props) {
  const language = CODING_LANGUAGES.find(l => l.id === (draft.coding_language || "auto"))?.label || "Auto-detect";
  return <aside className="prep-review-column"><section className="prep-review" aria-labelledby="prep-review-title">
    <div className="prep-review-top"><span>04 / REVIEW</span><ShieldCheck size={20} /></div><p className="ws-eyebrow">YOUR CONVERSATION, PREPARED</p><h3 id="prep-review-title">{purposeLabel || "Your next conversation"}</h3><p className="prep-review-objective">{draft.objective || "A clear objective makes the guidance more useful. Add yours to get started."}</p>
    <div className="prep-review-context"><FileCheck2 size={17} /><span>{names.length} context document{names.length === 1 ? "" : "s"} selected{!names.length ? " · General assistance" : ""}</span></div>
    {names.length > 0 && <ul className="prep-review-documents">{names.map((name, i) => <li key={i}><Check size={12} /><span>{name}</span></li>)}</ul>}
    <dl className="prep-review-details"><div><dt>Code Assist preference</dt><dd>{draft.purpose === "job_interview" && draft.technical_interview ? `Technical interview · ${language}` : "No technical preference"}</dd></div><div><dt>Conversation data</dt><dd>Live context and cues are session-only.</dd></div></dl>
    <div className="prep-readiness" role="status" data-ready={saved}><span />{saved ? "Saved & selected for Desktop" : dirty ? "Unsaved changes" : draft.purpose && draft.objective.trim() ? "Ready to save" : "Preparation in progress"}</div>
    <button className="ws-primary-button" type="button" disabled={disabled} onClick={onSave}>{busy ? "Saving…" : "Save & use preparation"}<ArrowUpRight size={16} /></button>
    <p className="prep-save-help">Save your choices, then review them in MeetGuide Desktop before Start Session.</p>
  </section><div className="prep-handoff"><Monitor size={22} strokeWidth={1.4} /><h4>Your next step is Desktop.</h4><p>Your purpose, objective and selected context accompany the live session. MeetGuide listens only after you start it there.</p><a href="#desktop-companion">How to continue <ArrowDownRight size={15} /></a></div></aside>;
}
