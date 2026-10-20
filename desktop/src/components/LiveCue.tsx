import { useEffect, useState } from "react";
import { clearCue, prepareCue, readCue, type CueSnapshot } from "../lib/cue";
import type { MeaningfulEvent } from "../lib/understanding";

export function LiveCue({ sessionId, event, active, onClear }: { sessionId: number; event?: MeaningfulEvent; active: boolean; onClear?: (sessionId: number, eventId: number) => void }) {
  const [view, setView] = useState<CueSnapshot | null>(null);
  const [failure, setFailure] = useState<{ key: string; text: string } | null>(null);
  const [attempt, setAttempt] = useState({ key: "", count: 0 });
  const [dismissed, setDismissed] = useState("");
  const [clearing, setClearing] = useState(false);
  const question = event?.type === "question" && event.speaker === "them" && event.confidence >= 0.82 && Number.isFinite(event.confidence) ? event : undefined;
  const eventId = question?.id;
  const key = `${sessionId}:${eventId}`;
  const retryAttempt = attempt.key === key ? attempt.count : 0;
  useEffect(() => {
    setView(null); setFailure(null);
    if (!active || eventId === undefined || dismissed === key) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const next = await readCue(); if (alive) { setView(next); setFailure(null); } }
      catch { if (alive) setFailure({ key, text: "Unable to read Live Cue. Please retry." }); }
      if (alive) timer = setTimeout(() => { void poll(); }, 200);
    }
    void (async () => {
      try { await prepareCue(sessionId, eventId, retryAttempt > 0); if (alive) void poll(); }
      catch { if (alive) setFailure({ key, text: "Unable to prepare an answer. Please retry." }); }
    })();
    return () => { alive = false; clearTimeout(timer); };
  }, [active, sessionId, eventId, retryAttempt, key, dismissed]);
  if (!active || !question) return null;
  // Matching is checked during render, before effects, so an old answer never flashes for a new question.
  const current = view?.sessionId === sessionId && view.eventId === eventId ? view : null;
  const error = failure?.key === key ? failure.text : current?.status === "error" ? current.error : null;
  const idle = dismissed === key || current?.status === "idle";
  async function dismiss() {
    setClearing(true);
    try {
      await clearCue(sessionId, question!.id);
      setDismissed(key); setView(null); setFailure(null);
      onClear?.(sessionId, question!.id);
    } catch { setFailure({ key, text: "Unable to clear Live Cue. Please retry Clear." }); }
    finally { setClearing(false); }
  }
  return <section className="live-cue" aria-label="Live Cue">
    <div className="live-cue-heading"><h3>Live Cue</h3><div className="live-cue-actions"><span>{idle ? "Listening" : current?.status === "ready" ? "Ready to speak" : "Answer"}</span>{!idle && <button className="audio-refresh" aria-label="Clear Live Cue" disabled={clearing} onClick={() => void dismiss()}>{clearing ? "Clearing…" : "Clear"}</button>}</div></div>
    {!idle && <p className="live-cue-question">{question.text}</p>}
    {idle ? <p className="transcript-footnote" role="status">Listening for the next question.</p> : error ? <><p role="alert">{error}</p><button className="audio-refresh" onClick={() => setAttempt((value) => ({ key, count: value.key === key ? value.count + 1 : 1 }))}>Retry answer</button></> : current?.status === "ready" && current.answer ? <>
      <div className="live-cue-answer">{current.answer.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div>
      <p className="transcript-footnote">{current.grounding === "document_supported" ? `Uses ${current.sourceCount} document excerpt${current.sourceCount === 1 ? "" : "s"}` : "General approach · No personal experience claimed"}</p>
    </> : <p className="transcript-footnote" aria-live="polite">Preparing answer…</p>}
  </section>;
}
