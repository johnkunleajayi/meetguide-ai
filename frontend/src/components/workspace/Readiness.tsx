import { ArrowRight, AudioLines, Check, FileText, LoaderCircle } from "lucide-react";
import type { ContextLibraryState } from "../../hooks/useContextLibrary";

export function Readiness({ library }: { library: ContextLibraryState }) {
  const { documents, loading, loadError } = library;
  const ready = documents.filter(document => document.status === "ready").length;
  const pending = documents.filter(document => document.status === "deleting").length;
  const state = loading ? "loading" : loadError ? "unknown" : ready ? "ready" : pending ? "attention" : "empty";
  const title = loading ? "Checking your context…" : loadError ? "Context status unavailable." : ready ? "Your context is ready." : pending ? "Your library needs attention." : "Start with your experience.";
  return <section className="ws-readiness" data-state={state} aria-labelledby="readiness-title">
    <div className="ws-readiness-copy"><p className="ws-eyebrow">MEETGUIDE PREPARATION</p><div className="ws-readiness-title">{ready > 0 && !loading && !loadError ? <Check size={19} aria-hidden="true" /> : null}<h2 id="readiness-title">{title}</h2></div>
      <div className="ws-readiness-summary" aria-live="polite">{loading ? <p>Loading the context available to your account.</p> : loadError ? <p>Refresh your Context Library to check what is available.</p> : <>
        <p>{ready ? `${ready} context document${ready === 1 ? "" : "s"} ready` : pending ? "No ready context documents" : "Add your résumé to personalize your Live Cues."}</p>
        {pending > 0 && <span>{pending} document{pending === 1 ? "" : "s"} awaiting deletion. Retry in your library.</span>}
      </>}</div>
      <a className="ws-inline-link" href="#context-library">{ready ? "Manage your context" : "Open Context Library"}<ArrowRight size={14} aria-hidden="true" /></a>
    </div>
    <div className="ws-context-path" aria-label="Your résumé provides relevant experience for personalized Live Cues"><div className="ws-context-node"><FileText size={24} strokeWidth={1.3} aria-hidden="true" /><span>Your résumé</span></div><div className="ws-context-connection"><span /><span>{loading ? <LoaderCircle size={14} aria-hidden="true" /> : ready && !loadError ? <Check size={14} aria-hidden="true" /> : <ArrowRight size={14} aria-hidden="true" />}</span><span /></div><div className="ws-context-node ws-context-meetguide"><AudioLines size={24} strokeWidth={1.4} aria-hidden="true" /><span>Relevant Live Cues</span></div><p>Relevant experience. A more personal response.</p></div>
  </section>;
}
