import { useEffect, useRef, useState } from "react";
import { Braces, BriefcaseBusiness, Check, ChevronRight, CircleUserRound, FolderOpen, MessagesSquare, Plus, Presentation, Target, Users } from "lucide-react";
import { usePreparations } from "../../hooks/usePreparations";
import type { ContextLibraryState } from "../../hooks/useContextLibrary";
import { PURPOSES, CODING_LANGUAGES, type PreparationInput } from "../../lib/preparations";
import { PreparationContext } from "./PreparationContext";
import { PreparationReview } from "./PreparationReview";
const icons = [CircleUserRound, BriefcaseBusiness, MessagesSquare, Users, Presentation, Target];
const toDraft = (item: PreparationInput): PreparationInput => ({ purpose: item.purpose, objective: item.objective, documents: item.documents, technical_interview: item.technical_interview || false, coding_language: item.coding_language || "auto" });
const empty = (): PreparationInput => ({ purpose: "", objective: "", documents: [] });
export function PreparationEditor({ library }: { library: ContextLibraryState }) {
  const preparations = usePreparations();
  const [id, setId] = useState("");
  const [draft, setDraft] = useState(empty);
  const [notice, setNotice] = useState("");
  const initialized = useRef(false);
  useEffect(() => {
    if (preparations.loading || initialized.current) return;
    initialized.current = true;
    const active = preparations.items.find(p => p.active);
    if (active) { setId(active.id); setDraft(toDraft(active)); }
  }, [preparations.loading, preparations.items]);
  const active = preparations.items.find(p => p.active);
  const current = preparations.items.find(p => p.id === id);
  const dirty = !!current && JSON.stringify(toDraft(current)) !== JSON.stringify(toDraft(draft));
  const purpose = PURPOSES.find(p => p.id === draft.purpose);
  const locked = preparations.busy || preparations.loading || library.loading || library.operation !== null;
  const select = (document_id: string, checked: boolean, context_role = "other") => {
    setNotice("");
    setDraft(previous => ({ ...previous, documents: [...previous.documents.filter(d => d.document_id !== document_id), ...(checked ? [{ document_id, context_role }] : [])] }));
  };
  const selected = draft.documents.filter(link => library.documents.some(doc => doc.id === link.document_id && doc.status === "ready"));
  const chooseSaved = (value: string) => { const item = preparations.items.find(p => p.id === value); setId(item?.id || ""); setDraft(item ? toDraft(item) : empty()); setNotice(""); };
  const save = async () => {
    const result = await preparations.save({ ...draft, documents: selected }, id || undefined);
    if (result) { const saved = result.item; setId(saved.id); setDraft(toDraft(saved)); setNotice(result.activated ? "Preparation saved and selected for Desktop. Review it there before starting." : ""); }
  };
  return <section className="prep-editor" aria-label="MeetGuide preparation" data-purpose={draft.purpose || "none"}>
    <div className="prep-editor-header"><div><p className="ws-eyebrow">MEETGUIDE PREPARATION</p><h2>What are you preparing for?</h2><p>A purpose. An objective. The context that belongs with it.</p></div><div className="prep-saved-controls"><label className="prep-field"><span><FolderOpen size={13} />Saved preparations</span><select aria-label="Saved preparations" disabled={locked} value={id} onChange={event => chooseSaved(event.target.value)}><option value="">New preparation</option>{preparations.items.map(p => <option key={p.id} value={p.id}>{p.objective}{p.active ? " · Active for Desktop" : ""}</option>)}</select></label><button type="button" className="ws-icon-button prep-new" disabled={locked} onClick={() => chooseSaved("")}><Plus size={16} />New</button></div></div>
    <nav className="prep-progress" aria-label="Preparation steps">{[["Purpose", "prep-purpose", !!draft.purpose], ["Objective", "prep-objective", !!draft.objective.trim()], ["Context", "context-library", selected.length > 0], ["Review", "prep-review-title", active?.id === id && !dirty]].map(([label, anchor, done], i) => <a key={String(anchor)} href={`#${anchor}`} data-done={!!done}><span>{done ? <Check size={12} /> : `0${i + 1}`}</span>{label}<ChevronRight size={13} /></a>)}</nav>
    {preparations.loading && <p role="status">Loading preparations…</p>}{preparations.error && <p className="ws-error" role="alert">{preparations.error}</p>}
    <div className="prep-editor-grid"><div className="prep-canvas">
      <section id="prep-purpose" className="prep-step"><div className="prep-step-heading"><span>01</span><div><h3>The conversation</h3><p>Choose a purpose. Make the assistance relevant.</p></div></div><fieldset className="prep-purposes" disabled={locked}><legend className="ws-visually-hidden">Session purpose</legend>{PURPOSES.map((p, i) => { const Icon = icons[i]; return <label key={p.id} className="prep-purpose" data-selected={draft.purpose === p.id}><input type="radio" name="purpose" value={p.id} checked={draft.purpose === p.id} onChange={() => { setDraft(v => ({ ...v, purpose: p.id })); setNotice(""); }} /><Icon size={21} strokeWidth={1.5} aria-hidden="true" /><span>{p.label}</span><Check size={13} className="prep-purpose-check" aria-hidden="true" /></label>; })}</fieldset>
      {draft.purpose === "job_interview" && <fieldset className="prep-technical" disabled={locked}><legend>Optional interview preferences</legend><label><input type="checkbox" aria-label="Technical/Coding interview" checked={draft.technical_interview || false} onChange={event => setDraft(v => ({ ...v, technical_interview: event.target.checked }))} /><Braces size={17} aria-hidden="true" /><span>Technical/Coding interview<small>Include your preferred language when relevant.</small></span></label>{draft.technical_interview && <label className="prep-field">Preferred coding language<select aria-label="Preferred coding language" value={draft.coding_language || "auto"} onChange={event => setDraft(v => ({ ...v, coding_language: event.target.value }))}>{CODING_LANGUAGES.map(language => <option key={language.id} value={language.id}>{language.label}</option>)}</select><small>A language requested in the conversation takes priority.</small></label>}</fieldset>}
      </section>
      <section id="prep-objective" className="prep-step prep-objective-section"><div className="prep-step-heading"><span>02</span><div><h3>Your objective</h3><p>What would make this conversation a good one?</p></div></div><label className="prep-field prep-objective-field"><span className="ws-visually-hidden">2. What would you like to accomplish?</span><textarea disabled={locked} maxLength={600} value={draft.objective} onChange={event => { setDraft(v => ({ ...v, objective: event.target.value })); setNotice(""); }} placeholder="Describe the conversation, what matters, and what you want to accomplish." rows={4} /></label><div className="prep-objective-meta"><span>A little specificity gives MeetGuide useful direction.</span><span>{draft.objective.length} / 600</span></div></section>
      <PreparationContext library={library} links={draft.documents} locked={locked} purposeLabel={purpose?.label || ""} guidance={purpose?.guidance || ""} onSelect={select} />
    </div><PreparationReview draft={draft} purposeLabel={purpose?.label || (draft.purpose ? draft.purpose.replaceAll("_", " ") : "")} names={selected.map(link => library.documents.find(doc => doc.id === link.document_id)!.name)} busy={preparations.busy} disabled={locked || library.loadError || !draft.purpose || !draft.objective.trim()} saved={!!active && active.id === id && !dirty} dirty={dirty} onSave={() => void save()} /></div>
    {notice && <p role="status" className="ws-notice prep-save-notice">{notice}</p>}
    {active && <p className="prep-active">Desktop preparation: <strong>{active.objective}</strong>. Saved changes apply to the next live session; an ongoing session keeps its starting context.</p>}
  </section>;
}
