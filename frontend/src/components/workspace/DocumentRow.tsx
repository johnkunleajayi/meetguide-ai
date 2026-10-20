import { FileText, LoaderCircle, Trash2 } from "lucide-react";
import type { ContextDocument } from "../../lib/context";

export function DocumentRow({ document, disabled, deleting, onDelete }: {
  document: ContextDocument; disabled: boolean; deleting: boolean; onDelete: () => void;
}) {
  const format = document.media_type === "application/pdf" ? "PDF" : document.media_type === "text/plain" ? "TXT" : "DOCX";
  const bytes = document.size_bytes;
  const size = bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return <li className="ws-document-row">
    <div className="ws-document-icon"><FileText size={21} strokeWidth={1.4} aria-hidden="true" /><span>{format}</span></div>
    <div className="ws-document-info"><strong>{document.name}</strong><p>{document.context_type === "resume" ? "Résumé / CV" : "Context document"}<span>·</span>{size}</p></div>
    <span className="ws-document-status" data-ready={document.status === "ready"}><i />{document.status === "ready" ? "Ready" : "Deletion pending — retry delete"}</span>
    <button type="button" className="ws-delete-button" disabled={disabled} aria-label={`Delete ${document.name}`} onClick={onDelete}>{deleting ? <LoaderCircle className="ws-spinner" size={16} aria-hidden="true" /> : <Trash2 size={16} strokeWidth={1.5} aria-hidden="true" />}<span>{deleting ? "Deleting…" : "Delete"}</span></button>
  </li>;
}
