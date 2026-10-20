import { useEffect, useRef, useState } from "react";
import { usePreparations } from "../../hooks/usePreparations";
import type { ContextLibraryState } from "../../hooks/useContextLibrary";
import { CATEGORIES, PURPOSES, categoryLabel, type PreparationInput } from "../../lib/preparations";
import { DocumentUpload } from "./DocumentUpload";

const empty = (): PreparationInput => ({ purpose: "", objective: "", documents: [] });
export function PreparationEditor({ library }: { library: ContextLibraryState }) {
  const preparations = usePreparations();
  const [id, setId] = useState("");
  const [draft, setDraft] = useState(empty);
  const [notice, setNotice] = useState("");
  const [uploadType, setUploadType] = useState("other");
  const initialized = useRef(false);
  useEffect(() => {
    if (preparations.loading || initialized.current) return;
    initialized.current = true;
    const active = preparations.items.find(p => p.active);
    if (active) { setId(active.id); setDraft({ purpose: active.purpose, objective: active.objective, documents: active.documents }); }
  }, [preparations.loading, preparations.items]);
  const active = preparations.items.find(p => p.active);
  const purpose = PURPOSES.find(p => p.id === draft.purpose);
  const locked = preparations.busy || preparations.loading || library.loading || library.operation !== null;
  const select = (document_id: string, checked: boolean, context_role = "other") => {
    setNotice("");
    setDraft(previous => ({ ...previous, documents: [...previous.documents.filter(d => d.document_id !== document_id), ...(checked ? [{ document_id, context_role }] : [])] }));
  };
  const selected = draft.documents.filter(link => library.documents.some(doc => doc.id === link.document_id && doc.status === "ready"));
  return <section className="prep-editor" aria-label="MeetGuide preparation">
    <div className="ws-section-heading"><div><p className="ws-eyebrow">MEETGUIDE PREPARATION</p><h2>What are you preparing for?</h2><p>Give this conversation a purpose. Add only the context it needs.</p></div></div>
    {preparations.loading && <p role="status">Loading preparations…</p>}
    {preparations.error && <p className="ws-error" role="alert">{preparations.error}</p>}
    <label className="prep-field">Saved preparations<select disabled={locked} value={id} onChange={event => {
      const item = preparations.items.find(p => p.id === event.target.value);
      setId(item?.id || ""); setDraft(item ? { purpose: item.purpose, objective: item.objective, documents: item.documents } : empty()); setNotice("");
    }}><option value="">New preparation</option>{preparations.items.map(p => <option key={p.id} value={p.id}>{p.objective}{p.active ? " · Active for Desktop" : ""}</option>)}</select></label>
    <fieldset className="prep-purposes" disabled={locked}><legend>1. Session purpose</legend>{PURPOSES.map(p => <label key={p.id} className="prep-purpose" data-selected={draft.purpose === p.id}><input type="radio" name="purpose" value={p.id} checked={draft.purpose === p.id} onChange={() => { setDraft(v => ({ ...v, purpose: p.id })); setNotice(""); }} />{p.label}</label>)}</fieldset>
    <label className="prep-field">2. What would you like to accomplish?<textarea disabled={locked} maxLength={600} value={draft.objective} onChange={event => { setDraft(v => ({ ...v, objective: event.target.value })); setNotice(""); }} placeholder="Describe the conversation and what you want help with." rows={3} /></label>
    <section id="context-library" aria-labelledby="session-context-title" className="prep-context">
      <h3 id="session-context-title">3. Relevant context</h3><p>Add anything MeetGuide should know for this session. Documents are optional.</p>
      <p className="prep-guidance"><strong>Suggested for {purpose?.label || "this session"}</strong><br />{purpose?.guidance || "Relevant professional context documents."}<br />PDF, DOCX or TXT only, including text-based exports of presentations. No PPTX upload.</p>
      <div className="prep-context-grid"><div><label className="prep-field">Context type for new document<select disabled={locked} value={uploadType} onChange={event => setUploadType(event.target.value)}>{CATEGORIES.map(c => <option value={c} key={c}>{categoryLabel(c)}</option>)}</select></label>
        <DocumentUpload library={{ ...library, upload: file => library.upload(file, uploadType, doc => select(doc.id, true, uploadType)) }} />
      </div><div className="prep-reusable"><h4>Choose existing or newly uploaded context</h4><p>Nothing is selected automatically.</p>
        {library.loading && <p role="status">Loading your documents…</p>}
        {library.error && <p role="alert">{library.error}</p>}
        <button type="button" className="ws-icon-button" disabled={locked} onClick={library.refresh}>Refresh documents</button>
        {!library.loading && !library.documents.length && <p>No documents yet. You can prepare a session without one.</p>}
        <ul className="prep-document-list">{library.documents.map(doc => {
          const link = draft.documents.find(d => d.document_id === doc.id);
          return <li key={doc.id}><label className="prep-document-select"><input type="checkbox" disabled={locked || doc.status !== "ready"} checked={!!link} onChange={event => select(doc.id, event.target.checked, doc.context_type)} /><span>{doc.name}<small>{categoryLabel(doc.context_type)} · {doc.status === "ready" ? "Ready" : "Deletion pending — retry delete"}</small></span></label>
            {link && <><label className="prep-field">Role for {doc.name}<select disabled={locked} value={link.context_role} onChange={event => select(doc.id, true, event.target.value)}>{[...new Set([...CATEGORIES, link.context_role])].map(c => <option key={c} value={c}>{categoryLabel(c)}</option>)}</select></label><button type="button" className="ws-icon-button" disabled={locked} onClick={() => select(doc.id, false)}>Remove from preparation</button></>}
            <button type="button" className="ws-icon-button" disabled={locked} aria-label={`Delete ${doc.name} from account`} onClick={async () => {
              if (window.confirm(`Delete ${doc.name} from your account and all preparations? This removes its file and extracted content.`) && await library.remove(doc.id)) select(doc.id, false);
            }}>Delete from account</button></li>;
        })}</ul>
      </div></div>
    </section>
    <section className="prep-review" aria-labelledby="prep-review-title"><div><p className="ws-eyebrow">4. PREPARATION SUMMARY</p><h3 id="prep-review-title">{purpose?.label || (draft.purpose ? draft.purpose.replaceAll("_", " ") : "Choose a purpose")}</h3><p>{draft.objective || "Add an objective above."}</p><span>{selected.length} context document{selected.length === 1 ? "" : "s"} selected{!selected.length ? " · General assistance" : ""}</span></div>
      <button className="ws-primary-button" type="button" disabled={locked || library.loadError || !draft.purpose || !draft.objective.trim()} onClick={async () => {
        const result = await preparations.save({ ...draft, documents: selected }, id || undefined);
        if (result) { const saved = result.item; setId(saved.id); setDraft({ purpose: saved.purpose, objective: saved.objective, documents: saved.documents }); setNotice(result.activated ? "Preparation saved and selected for Desktop. Review it there before starting." : ""); }
      }}>{preparations.busy ? "Saving…" : "Save & use preparation"}</button>
    </section>
    {notice && <p role="status" className="ws-notice">{notice}</p>}
    {active && <p className="prep-active">Desktop preparation: <strong>{active.objective}</strong>. Saved changes apply to the next live session; an ongoing session keeps its starting context.</p>}
    <p className="ws-library-privacy">Files are private to your account. Removing a selection keeps the reusable document. Deleting from your account removes its file, extracted text and preparation links.</p>
  </section>;
}
