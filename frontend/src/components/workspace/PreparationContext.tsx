import { useState } from "react";
import { Check, FileText, FolderOpen, LockKeyhole, RefreshCw, Trash2, X } from "lucide-react";
import type { ContextLibraryState } from "../../hooks/useContextLibrary";
import { CATEGORIES, categoryLabel, type Selection } from "../../lib/preparations";
import { DocumentUpload } from "./DocumentUpload";
interface Props { library: ContextLibraryState; links: Selection[]; locked: boolean; purposeLabel: string; guidance: string; onSelect: (id: string, checked: boolean, role?: string) => void }
export function PreparationContext({ library, links, locked, purposeLabel, guidance, onSelect }: Props) {
  const [uploadType, setUploadType] = useState("other");
  const [filter, setFilter] = useState<"all" | "selected">("all");
  const documents = library.documents.filter(doc => filter === "all" || links.some(link => link.document_id === doc.id));
  return <section id="context-library" aria-labelledby="session-context-title" className="prep-context prep-step">
    <div className="prep-step-heading"><span>03</span><div><h3 id="session-context-title">Relevant context</h3><p>What should MeetGuide bring to this conversation?</p></div><LockKeyhole size={16} aria-label="Private to your account" /></div>
    <p className="prep-guidance"><strong>Useful for {purposeLabel || "this conversation"}</strong><span>{guidance || "Relevant professional context. Documents are optional."}</span></p>
    <div className="prep-context-grid"><div className="prep-upload-column"><label className="prep-field">Context type for new document<select disabled={locked} value={uploadType} onChange={event => setUploadType(event.target.value)}>{CATEGORIES.map(c => <option value={c} key={c}>{categoryLabel(c)}</option>)}</select></label>
      <DocumentUpload library={{ ...library, loading: locked, upload: file => library.upload(file, uploadType, doc => onSelect(doc.id, true, uploadType)) }} />
    </div><div className="prep-reusable"><div className="prep-library-top"><div><FolderOpen size={17} /><h4>Reusable documents</h4></div><button type="button" className="ws-icon-button" aria-label="Refresh documents" disabled={locked} onClick={library.refresh}><RefreshCw size={15} /></button></div><p>Stored in your account. Used only when selected here.</p>
      <div className="prep-library-filters" aria-label="Document view"><button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All documents <span>{library.documents.length}</span></button><button type="button" aria-pressed={filter === "selected"} onClick={() => setFilter("selected")}>Selected <span>{links.length}</span></button></div>
      {library.loading && <p role="status">Loading your documents…</p>}
      {library.error && <p className="ws-error" role="alert">{library.error}</p>}
      {library.notice && <p className="ws-notice" role="status">{library.notice}</p>}
      {!library.loading && !documents.length && <div className="prep-library-empty"><FileText size={27} strokeWidth={1.2} /><h4>{filter === "selected" ? "Choose what comes with you." : "Start with what matters."}</h4><p>{filter === "selected" ? "No documents selected. Browse your reusable documents or add a new one." : "Add a brief, notes or relevant background. You can also prepare without a document."}</p>{filter === "selected" && <button type="button" className="ws-inline-link" onClick={() => setFilter("all")}>Browse documents</button>}</div>}
      <ul className="prep-document-list" aria-label="Reusable context documents">{documents.map(doc => { const link = links.find(item => item.document_id === doc.id); return <li key={doc.id} data-selected={!!link}>
        <label className="prep-document-select"><input type="checkbox" disabled={locked || doc.status !== "ready"} checked={!!link} onChange={event => onSelect(doc.id, event.target.checked, doc.context_type)} /><span className="prep-document-symbol"><FileText size={19} /></span><span>{doc.name}<small>{categoryLabel(doc.context_type)} · {(doc.size_bytes / 1024).toFixed(1)} KB · {doc.status === "ready" ? "Ready" : "Deletion pending — retry delete"}</small></span>{link && <Check size={14} className="prep-selected-check" aria-hidden="true" />}</label>
        {link && <div className="prep-document-role"><label className="prep-field">Context role<select aria-label={`Role for ${doc.name}`} disabled={locked} value={link.context_role} onChange={event => onSelect(doc.id, true, event.target.value)}>{[...new Set([...CATEGORIES, link.context_role])].map(c => <option key={c} value={c}>{categoryLabel(c)}</option>)}</select></label><button type="button" className="ws-icon-button" disabled={locked} onClick={() => onSelect(doc.id, false)}><X size={13} />Remove from preparation</button></div>}
        <div className="prep-document-account"><span>{link ? "Selected for this preparation" : "Not selected"}</span><button type="button" className="ws-icon-button prep-delete" disabled={locked} aria-label={`Delete ${doc.name} from account`} onClick={async () => { if (window.confirm(`Delete ${doc.name} from your account and all preparations? This removes its file and extracted content.`) && await library.remove(doc.id)) onSelect(doc.id, false); }}><Trash2 size={12} />Delete from account</button></div>
      </li>; })}</ul>
    </div></div>
    <p className="ws-library-privacy"><LockKeyhole size={13} /><span>Remove from preparation keeps the reusable file. Delete from account removes the file, extracted context and all preparation links. PDF, DOCX or TXT · up to 5 MB.</span></p>
  </section>;
}
