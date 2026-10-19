import { useEffect, useRef, useState, type FormEvent } from "react";
import { deleteDocument, listDocuments, uploadDocument, type ContextDocument } from "../lib/context";
import { Eyebrow } from "./ui";

export function ContextLibrary() {
  const [documents, setDocuments] = useState<ContextDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const pending = useRef(false);

  useEffect(() => {
    const active = new AbortController(); controller.current = active;
    setLoading(true); setError("");
    listDocuments(active.signal).then((items) => { if (!active.signal.aborted) setDocuments(items); })
      .catch(() => { if (!active.signal.aborted) setError("Unable to load your documents. Please retry."); })
      .finally(() => { if (!active.signal.aborted) setLoading(false); });
    return () => active.abort();
  }, [attempt]);

  async function act(operation: (signal: AbortSignal) => Promise<void>) {
    if (pending.current || !controller.current) return;
    const signal = controller.current.signal;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try { await operation(signal); }
    catch (cause) { if (!signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to update your library. Please retry."); }
    finally { pending.current = false; if (!signal.aborted) setBusy(false); }
  }
  function upload(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) { setError("Choose a résumé file first."); return; }
    void act(async (signal) => {
      const document = await uploadDocument(file, signal);
      if (signal.aborted) return;
      setDocuments((items) => [document, ...items]); setNotice("Résumé added to your Context Library.");
      if (input.current) input.current.value = "";
    });
  }

  return <section className="context-library container" id="context-library" aria-labelledby="library-title">
    <div className="section-heading"><div><Eyebrow>YOUR CONTEXT</Eyebrow><h2 id="library-title">Context Library</h2></div><p>Keep your experience ready for future personalized assistance.</p></div>
    <div className="library-panel">
      <form onSubmit={upload} className="library-upload">
        <label htmlFor="resume-file">Upload résumé / CV</label>
        <p id="resume-help">PDF, DOCX or UTF-8 TXT · Up to 5 MB · Text-based documents only</p>
        <div className="library-upload-actions"><input id="resume-file" type="file" accept=".pdf,.docx,.txt" aria-describedby="resume-help" ref={input} disabled={busy || loading} /><button type="submit" className="button button-primary" disabled={busy || loading}>{busy ? "Working…" : "Upload résumé"}</button></div>
      </form>
      {loading && <p role="status">Loading your documents…</p>}
      {error && <div role="alert"><p>{error}</p><button type="button" className="sign-in" disabled={busy} onClick={() => setAttempt((value) => value + 1)}>Refresh documents</button></div>}
      {notice && <p role="status">{notice}</p>}
      {!loading && !error && !documents.length && <p className="library-empty">No documents yet. Add your résumé to get started.</p>}
      <ul className="library-documents">{documents.map((document) => <li key={document.id}>
        <div><strong>{document.name}</strong><p>Résumé / CV · {document.media_type === "application/pdf" ? "PDF" : document.media_type === "text/plain" ? "TXT" : "DOCX"} · {document.status === "ready" ? "Ready" : "Deletion pending — retry delete"}</p></div>
        <button type="button" className="sign-in" disabled={busy || loading} aria-label={`Delete ${document.name}`} onClick={() => {
          if (!window.confirm(`Delete ${document.name} and its extracted context?`)) return;
          void act(async (signal) => { await deleteDocument(document.id, signal); if (!signal.aborted) { setDocuments((items) => items.filter((item) => item.id !== document.id)); setNotice("Document and extracted context deleted."); } });
        }}>Delete</button>
      </li>)}</ul>
      <p className="library-privacy">Private to your account. Deleting a document removes its file and extracted context. No AI answers are generated.</p>
    </div>
  </section>;
}
