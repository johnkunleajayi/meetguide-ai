import { CueCard, primaryCueId } from "./CueCard";
import { DesktopIcon } from "./DesktopIcon";
import { useEffect, useRef, useState } from "react";
import { clearCue, prepareCue, readCue, subscribeCue, type CueSnapshot } from "../lib/cue";

export function LiveCue({ sessionId, active }: { sessionId: number; active: boolean }) {
  const [view, setView] = useState<CueSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);
  const generation = useRef(0);
  const removed = useRef(new Set<number>());
  const previousProgress = useRef(new Map<number, number>());
  const firstOutput = useRef(new Set<string>());
  const previousReady = useRef(new Set<number>());
  const following = useRef(true);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    generation.current += 1; setRemoving(null);
    setView(null); setError(null); setUnread(false);
    removed.current.clear(); previousReady.current.clear(); previousProgress.current.clear(); firstOutput.current.clear(); following.current = true;
    if (!active) return;
    let alive = true;
    let unlisten: (() => void) | undefined;
    let revision = 0;
    const apply = (next: CueSnapshot) => {
      if (alive && next.sessionId === sessionId) {
        setView({ ...next, cards: next.cards.filter(card => !removed.current.has(card.id)) });
      }
    };
    void (async () => {
      try {
        unlisten = await subscribeCue(next => { revision++; apply(next); });
        if (!alive) { unlisten(); return; }
        const ownRevision = revision;
        const initial = await readCue();
        if (revision === ownRevision) apply(initial);
      } catch { if (alive) setError("Unable to read Live Cues. Restart the session to retry."); }
    })();
    return () => { alive = false; unlisten?.(); };
  }, [active, sessionId]);
  const current = view?.sessionId === sessionId && active ? view : null;
  useEffect(() => {
    const ready = new Set(current?.cards.filter(card => card.status === "ready").map(card => card.id));
    const grew = current?.cards.some(card => card.status === "responding" && ((card.answer?.length || 0) + (card.codeAssist?.code.length || 0)) > (previousProgress.current.get(card.id) || 0));
    const arrived = grew || [...ready].some(id => !previousReady.current.has(id));
    previousProgress.current = new Map(current?.cards.map(card => [card.id, (card.answer?.length || 0) + (card.codeAssist?.code.length || 0)]));
    if (import.meta.env.DEV) {
      current?.cards.filter(card => card.answer && card.firstOutputAtUnixMs && !firstOutput.current.has(`${card.id}:${card.attempt}:${card.firstOutputAtUnixMs}`)).forEach(card => {
        firstOutput.current.add(`${card.id}:${card.attempt}:${card.firstOutputAtUnixMs}`);
        if (card.questionId && /^q-[a-zA-Z0-9-]{1,80}$/.test(card.questionId)) console.info("[MeetGuide Timing]", JSON.stringify({ stage:"cue_first_output_ui_observed",question_id:card.questionId,attempt:card.attempt,at_unix_ms:Date.now(),native_first_output_to_ui_observed_ms:Math.max(0,Date.now()-card.firstOutputAtUnixMs!) }));
      });
      current?.cards.filter(card => card.status === "ready" && !previousReady.current.has(card.id)).forEach(card => {
        if (card.questionId && /^q-[a-zA-Z0-9-]{1,80}$/.test(card.questionId)) {
          console.info("[MeetGuide Timing]", JSON.stringify({ stage: "cue_ui_observed", question_id: card.questionId, at_unix_ms: Date.now(), native_ready_to_ui_observed_ms: typeof card.readyAtUnixMs === "number" ? Math.max(0, Date.now() - card.readyAtUnixMs) : null }));
        }
      });
    }
    previousReady.current = ready;
    if (!arrived) return;
    if (following.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
    else setUnread(true);
  }, [current]);
  if (!active) return null;
  async function remove(id: number) {
    const ownGeneration = generation.current;
    setRemoving(id);
    try {
      await clearCue(sessionId, id);
      if (ownGeneration !== generation.current) return;
      removed.current.add(id);
      setView(value => value?.sessionId === sessionId ? { ...value, cards: value.cards.filter(card => card.id !== id) } : value);
      setError(null);
    } catch { if (ownGeneration === generation.current) setError("Unable to remove this cue. Please retry."); }
    finally { if (ownGeneration === generation.current) setRemoving(null); }
  }
  async function retry(id: number) {
    try { await prepareCue(sessionId, id, true); setError(null); }
    catch { setError("Unable to retry this answer. Please retry."); }
  }
  return <section aria-label="Live Cue feed" className="cue-feed" id="live-cues">
    <div className="cue-feed-heading"><div><span className="eyebrow">WORDS FOR THE MOMENT</span><h2>Live Cues</h2></div><span>Session only</span></div>
    {current?.notice && <p className="cue-notice" role="status">{current.notice.startsWith("Semantic understanding is unavailable.") ? "Conversation understanding is limited. Listening and question detection remain active." : current.notice}</p>}
    {error && <p role="alert">{error}</p>}
    <div className="cue-feed-scroll" ref={scroll} tabIndex={0} aria-label="Session cue cards" onScroll={() => {
      const element = scroll.current;
      if (element) { following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48; if (following.current) setUnread(false); }
    }}>
      {!current?.cards.length && <div className="cue-empty"><DesktopIcon name="audio" size={32} /><h3>Stay with the conversation.</h3><p>Listening for the next question.</p><span>Your guidance will appear here. You decide what to say.</span></div>}
      {current?.cards.map(card => <CueCard key={card.id} card={card} current={card.id === primaryCueId(current.cards)} removing={removing === card.id} onRemove={() => void remove(card.id)} onRetry={() => void retry(card.id)} />)}
    </div>
    {unread && <button className="audio-refresh" onClick={() => { following.current = true; setUnread(false); if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }}>New cue · View latest</button>}
  </section>;
}
