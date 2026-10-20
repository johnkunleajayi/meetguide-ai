import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { ArrowUpRight, FileText, LoaderCircle, UploadCloud, X } from "lucide-react";
import type { ContextLibraryState } from "../../hooks/useContextLibrary";

export function DocumentUpload({ library }: { library: ContextLibraryState }) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const input = useRef<HTMLInputElement>(null);
  const disabled = library.loading || library.operation !== null;
  function choose(files: FileList | File[]) {
    if (files.length !== 1) { setFile(null); if (input.current) input.current.value = ""; setError("Choose one document at a time."); return; }
    setFile(files[0]); setError("");
  }
  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); depth.current = 0; setDragging(false);
    if (!disabled) choose(event.dataTransfer.files);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) { setError("Choose a document file first."); return; }
    if (await library.upload(file)) { setFile(null); if (input.current) input.current.value = ""; }
  }
  return <form className="ws-upload" onSubmit={submit} aria-label="Upload context">
    <div className="ws-dropzone" data-dragging={dragging && !disabled} onDrop={drop}
      onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? "none" : "copy"; }}
      onDragEnter={event => { event.preventDefault(); depth.current++; if (!disabled) setDragging(true); }}
      onDragLeave={() => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDragging(false); }}>
      <div className="ws-upload-icon"><UploadCloud size={25} strokeWidth={1.4} aria-hidden="true" /></div>
      <h3>{dragging && !disabled ? "Drop your document here" : "Add context for this conversation."}</h3>
      <p>Drag a document here, or choose a file.</p>
      <input className="ws-file-input" id="resume-file" aria-label="Upload context document" type="file" accept=".pdf,.docx,.txt" aria-describedby="resume-help" ref={input} disabled={disabled} onChange={event => { if (event.target.files?.length) choose(event.target.files); }} />
      <label className="ws-choose-file" htmlFor="resume-file" aria-disabled={disabled}>Choose file</label>
      <p id="resume-help" className="ws-file-help">PDF, DOCX or UTF-8 TXT · Up to 5 MB<br />Text-based documents only</p>
    </div>
    {file && <div className="ws-selected-file"><FileText size={16} aria-hidden="true" /><span>{file.name}</span><button type="button" aria-label="Clear selected file" disabled={disabled} onClick={() => { setFile(null); if (input.current) input.current.value = ""; }}><X size={14} /></button></div>}
    {error && <p className="ws-local-error" role="alert">{error}</p>}
    <button type="submit" className="ws-primary-button" disabled={disabled}>{library.operation === "upload" ? <><LoaderCircle className="ws-spinner" size={15} aria-hidden="true" />Uploading…</> : <>Upload document<ArrowUpRight size={15} aria-hidden="true" /></>}</button>
    {library.operation === "upload" && <p className="ws-upload-state" role="status">Uploading and extracting your document…</p>}
  </form>;
}
