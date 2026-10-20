import { useEffect, useRef, useState } from "react";
import { deleteDocument, listDocuments, uploadDocument, type ContextDocument } from "../lib/context";

export function useContextLibrary() {
  const [documents, setDocuments] = useState<ContextDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [operation, setOperation] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const pending = useRef(false);

  useEffect(() => {
    const active = new AbortController(); controller.current = active;
    setLoading(true); setLoadError(false); setError("");
    listDocuments(active.signal).then(items => { if (!active.signal.aborted) setDocuments(items); })
      .catch(() => { if (!active.signal.aborted) { setLoadError(true); setError("Unable to load your documents. Please retry."); } })
      .finally(() => { if (!active.signal.aborted) setLoading(false); });
    return () => active.abort();
  }, [attempt]);

  async function run(kind: string, action: (signal: AbortSignal) => Promise<void>) {
    if (pending.current || !controller.current || controller.current.signal.aborted) return false;
    const signal = controller.current.signal;
    pending.current = true; setOperation(kind); setError(""); setNotice("");
    try { await action(signal); return !signal.aborted; }
    catch (cause) {
      if (!signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to update your library. Please retry.");
      return false;
    } finally {
      pending.current = false;
      if (!signal.aborted) setOperation(null);
    }
  }

  function upload(file: File, contextType = "other", onUploaded?: (doc: ContextDocument) => void) {
    return run("upload", async signal => {
      const document = await uploadDocument(file, signal, contextType);
      if (!signal.aborted) {
        setDocuments(items => [document, ...items]);
        setNotice("Document added to your reusable context.");
        onUploaded?.(document);
      }
    });
  }
  function remove(id: string) {
    return run(id, async signal => {
      await deleteDocument(id, signal);
      if (!signal.aborted) {
        setDocuments(items => items.filter(item => item.id !== id));
        setNotice("Document and extracted context deleted.");
      }
    });
  }
  return { documents, loading, loadError, operation, error, notice, upload, remove, refresh: () => setAttempt(value => value + 1) };
}
export type ContextLibraryState = ReturnType<typeof useContextLibrary>;
