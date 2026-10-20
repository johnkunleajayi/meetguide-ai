import { FileText, LockKeyhole, RefreshCw } from "lucide-react";
import { useContextLibrary, type ContextLibraryState } from "../hooks/useContextLibrary";
import { DocumentUpload } from "./workspace/DocumentUpload";
import { DocumentRow } from "./workspace/DocumentRow";

export function ContextLibrary({ library }: { library?: ContextLibraryState }) {
  return library ? <LibraryView library={library} /> : <StandaloneLibrary />;
}
function StandaloneLibrary() {
  const library = useContextLibrary();
  return <LibraryView library={library} />;
}
function LibraryView({ library }: { library: ContextLibraryState }) {
  const { documents, loading, operation, error, notice, refresh, remove } = library;
  const disabled = loading || operation !== null;
  return <section className="context-library ws-library" id="context-library" aria-labelledby="library-title">
    <div className="ws-section-heading"><div><p className="ws-eyebrow">REUSABLE CONTEXT</p><h2 id="library-title">Context Library</h2><p>Choose relevant documents within each preparation.</p></div><span className="ws-private-label"><LockKeyhole size={12} aria-hidden="true" />Private to you</span></div>
    <div className="ws-library-layout">
      <DocumentUpload library={library} />
      <div className="ws-document-area">
        <div className="ws-document-heading"><h3>Your documents</h3><button type="button" className="ws-icon-button" aria-label="Refresh documents" disabled={disabled} onClick={refresh}><RefreshCw size={15} aria-hidden="true" /></button></div>
        {loading && <p className="ws-library-loading" role="status">Loading your documents…</p>}
        {error && <div className="ws-error" role="alert"><p>{error}</p><button type="button" disabled={disabled} onClick={refresh}>Refresh documents</button></div>}
        {notice && <p className="ws-notice" role="status">{notice}</p>}
        {!loading && !error && !documents.length && <div className="ws-empty-library"><div className="ws-empty-document"><FileText size={28} strokeWidth={1} aria-hidden="true" /></div><h3>Keep useful context available.</h3><p className="library-empty">No documents yet. You can prepare a session without one.</p><span>Documents are only used when selected for a preparation.</span></div>}
        <ul className="ws-documents" aria-label="Your context documents">{documents.map(document => <DocumentRow key={document.id} document={document} disabled={disabled} deleting={operation === document.id} onDelete={() => {
          if (window.confirm(`Delete ${document.name} and its extracted context?`)) void remove(document.id);
        }} />)}</ul>
        <p className="ws-library-privacy"><LockKeyhole size={12} aria-hidden="true" /><span>Private to your account. Deleting a document removes its file and extracted context. No AI answers are generated in this workspace.</span></p>
      </div>
    </div>
  </section>;
}
