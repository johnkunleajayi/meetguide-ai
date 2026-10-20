import { useEffect, useState } from "react";
import { activatePreparation, purposeLabel, readPreparations, type Preparation } from "../lib/preparation";

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
    readPreparations().then(next => { if (alive) { setItems(next); onChange(next.find(p => p.active) || null); } }).catch(() => { if (alive) setError("Unable to load preparations. Check the backend, then refresh."); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [authenticated, revision, onChange]);
  if (!authenticated) return null;
  return <section className="preparation-panel" aria-label="Session preparation">
    <div className="live-cue-heading"><h3>Prepared for</h3>{locked && <span>Fixed for this session</span>}</div>
    {value ? <><strong>{purposeLabel(value.purpose)}</strong><p className="preparation-objective">{value.objective}</p><p>{value.documents.length} context document{value.documents.length === 1 ? "" : "s"}{value.documents.length ? "" : " · General assistance"}</p></> : <p>{busy ? "Loading preparation…" : "Create a preparation in your web workspace, then select it here. No résumé is required."}</p>}
    {!locked && <><label className="audio-field">Change preparation<select disabled={busy} value={value?.id || ""} onChange={async event => {
      const next = items.find(p => p.id === event.target.value);
      if (!next) { onChange(null); return; }
      setBusy(true); setError(""); onChange(null);
      try { await activatePreparation(next.id); onChange(next); } catch { setError("Unable to select preparation. Refresh and retry."); }
      finally { setBusy(false); }
    }}><option value="">Choose a preparation</option>{items.map(p => <option key={p.id} value={p.id}>{purposeLabel(p.purpose)} — {p.objective}</option>)}</select></label><button type="button" className="audio-refresh" disabled={busy} onClick={() => setRevision(v => v + 1)}>Refresh preparations</button></>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
