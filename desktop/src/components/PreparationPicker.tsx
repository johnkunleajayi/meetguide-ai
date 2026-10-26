import { DesktopIcon } from "./DesktopIcon";
import { useEffect, useState } from "react";
import { activatePreparation, purposeLabel, codingLanguageLabel, readPreparations, type Preparation } from "../lib/preparation";

export function PreparationPicker({ authenticated, locked, value, onChange }: { authenticated: boolean; locked: boolean; value: Preparation | null; onChange: (value: Preparation | null) => void }) {
  const [items, setItems] = useState<Preparation[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    onChange(null); setItems([]); setError("");
    if (!authenticated) return;
    setBusy(true);
    readPreparations().then(next => { if (alive) { setItems(next); onChange(next.find(p => p.active) || null); } }).catch(() => { if (alive) setError("Unable to load preparations. Refresh to try again."); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [authenticated, revision, onChange]);
  if (!authenticated) return null;
  return <section className="preparation-panel" aria-label="Session preparation" data-locked={locked}>
    <div className="setup-section-heading"><span>{locked ? "ACTIVE PREPARATION" : "01 / PREPARATION"}</span>{locked && <span className="preparation-fixed"><DesktopIcon name="check" size={12} />Fixed for this session</span>}</div>
    {value ? locked ? <details className="live-preparation"><summary><strong>{purposeLabel(value.purpose)}</strong><span>{value.documents.length} context document{value.documents.length === 1 ? "" : "s"}<DesktopIcon name="chevron" size={14} /></span></summary><PreparationContent value={value} compact /></details> : <PreparationContent value={value} /> : <div className="preparation-empty"><DesktopIcon name="document" size={27} /><h2>{busy ? "Loading preparation…" : "Bring a little preparation."}</h2><p>Create a preparation in your web workspace, then select it here.</p></div>}
    {!locked && <div className="preparation-actions"><details className="preparation-switch"><summary>Change preparation<DesktopIcon name="chevron" size={14} /></summary><label className="audio-field">Change preparation<select disabled={busy} value={value?.id || ""} onChange={async event => {
      const next = items.find(p => p.id === event.target.value);
      if (!next) { onChange(null); return; }
      setBusy(true); setError(""); onChange(null);
      try { await activatePreparation(next.id); onChange(next); } catch { setError("Unable to select preparation. Refresh and retry."); }
      finally { setBusy(false); }
    }}><option value="">Choose a preparation</option>{items.map(p => <option key={p.id} value={p.id}>{purposeLabel(p.purpose)} — {p.objective}</option>)}</select></label></details><button type="button" className="audio-refresh" disabled={busy} onClick={() => setRevision(v => v + 1)}><DesktopIcon name="refresh" size={13} />Refresh preparations</button></div>}
    {error && <p role="alert">{error}</p>}
  </section>;
}


function PreparationContent({ value, compact = false }: { value: Preparation; compact?: boolean }) {
  return <>
    {!compact && <strong className="preparation-purpose">{purposeLabel(value.purpose)}</strong>}
    <p className="preparation-objective" title={value.objective}>{value.objective}</p>
    <div className="preparation-metadata">
      {!compact && <span><DesktopIcon name="document" size={14} />{value.documents.length} context document{value.documents.length === 1 ? "" : "s"}{value.documents.length ? "" : " · General assistance"}</span>}
      {value.purpose === "job_interview" && value.technical_interview ? <span><DesktopIcon name="code" size={14} />Technical/Coding interview · {codingLanguageLabel(value.coding_language || "auto")}</span> : <span>Conversation assistance · no coding preference</span>}
    </div>
  </>;
}
