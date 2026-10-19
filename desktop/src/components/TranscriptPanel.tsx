import { useEffect, useRef, useState } from "react";
import { readTranscript, sourceLabel, type TranscriptSnapshot } from "../lib/transcription";

export function TranscriptPanel({ authenticated }: { authenticated: boolean }) {
  const [snapshot, setSnapshot] = useState<TranscriptSnapshot | null>(null);
  const [error, setError] = useState(false);
  const [following, setFollowing] = useState(true);
  const follow = useRef(true);
  const scroller = useRef<HTMLDivElement>(null);
  const session = useRef(0);

  useEffect(() => {
    if (!authenticated) { setSnapshot(null); setError(false); session.current = 0; return; }
    let active = true;
    let after = 0;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await readTranscript(after);
        if (active) {
          setError(false);
          if (next) {
            after = next.version;
            if (next.sessionId !== session.current) {
              session.current = next.sessionId; follow.current = true; setFollowing(true);
            }
            setSnapshot(next);
          }
        }
      } catch { if (active) setError(true); }
      if (active) timer = setTimeout(() => { void poll(); }, 200);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [authenticated]);

  useEffect(() => {
    if (follow.current && scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [snapshot]);

  return <section className="transcript-panel" aria-label="Live transcript">
    <div className="transcript-heading"><h2>Live transcript</h2><span>Session only</span></div>
    <div className="transcript-connections" aria-live="polite">
      {snapshot?.streams.map((stream) => <div key={stream.source}>
        <span>{sourceLabel(stream.source)} · {stream.state}</span>
        {stream.message && <p className="transcript-message" role={stream.state === "error" ? "alert" : undefined}>{stream.message}</p>}
        {stream.droppedChunks > 0 && <p className="transcript-message">Audio was dropped during a connection gap.</p>}
      </div>)}
      {error && <p role="alert">Unable to read transcription status. Check the desktop connection.</p>}
    </div>
    <div className="transcript-scroll" ref={scroller} tabIndex={0} aria-label="Conversation transcript" onScroll={() => {
      const element = scroller.current;
      if (!element) return;
      const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 48;
      follow.current = nearBottom; setFollowing(nearBottom);
    }}>
      {!snapshot?.entries.length && <p className="transcript-placeholder">Start a session to see spoken words here. System Audio appears as Them; Microphone as You.</p>}
      {snapshot?.entries.map((entry) => <article key={entry.id} className={`transcript-entry${entry.finalText ? "" : " is-partial"}`}>
        <div className="transcript-entry-label"><strong>{sourceLabel(entry.source)}</strong><span>{entry.interrupted ? "Interrupted" : entry.finalText ? "Final" : "Listening…"}</span></div>
        <p>{entry.text}</p>
      </article>)}
    </div>
    {!following && <button className="audio-refresh" onClick={() => { follow.current = true; setFollowing(true); if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight; }}>Follow latest</button>}
    {!!snapshot?.trimmed && <p className="transcript-footnote">Showing recent conversation. Older entries are discarded to keep memory bounded.</p>}
    <p className="transcript-footnote">Audio is sent for transcription. MeetGuide keeps text in memory for this session; a new session or sign-out clears it.</p>
  </section>;
}
