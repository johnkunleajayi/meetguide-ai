import { LiveCue } from "./LiveCue";
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

  const question = snapshot?.understanding.events.filter((event) => event.type === "question" && event.speaker === "them").at(-1);
  return <div className="conversation-workspace" data-active={authenticated && !!snapshot?.understanding.active}>
    <section className="transcript-panel" id="conversation" aria-label="Live transcript">
      <div className="transcript-heading"><h2>Conversation</h2><span>Session only</span></div>
      <div className="transcript-connections" aria-live="polite">
        {snapshot?.streams.map(stream => <div key={stream.source} data-state={stream.state}><span><i aria-hidden="true" />{sourceLabel(stream.source)} · {streamLabel(stream.state)}</span>{stream.message && <p className="transcript-message" role={stream.state === "error" ? "alert" : undefined}>{friendlyTranscriptionMessage(stream.message)}</p>}{stream.droppedChunks > 0 && <p className="transcript-message">Audio was dropped during a connection gap.</p>}</div>)}
        {error && <p role="alert">Unable to read transcription status. Check the desktop connection.</p>}
      </div>
      {question && authenticated && snapshot?.understanding.active && <aside className="question-indicator" role="status"><strong>Question detected</strong><p>{question.text}</p></aside>}
      <div className="transcript-scroll" ref={scroller} tabIndex={0} aria-label="Conversation transcript" onScroll={() => { const element = scroller.current; if (!element) return; const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 48; follow.current = nearBottom; setFollowing(nearBottom); }}>
        {!snapshot?.entries.length && <p className="transcript-placeholder">{snapshot?.understanding.active ? "Waiting for spoken words. Their audio appears as Them; your microphone as You." : "Start a session to see spoken words here. System Audio appears as Them; Microphone as You."}</p>}
        {snapshot?.entries.map(entry => <article key={entry.id} data-speaker={entry.source} className={`transcript-entry${entry.finalText ? "" : " is-partial"}`}><div className="transcript-entry-label"><strong>{sourceLabel(entry.source)}</strong><span>{entry.interrupted ? "Interrupted" : entry.finalText ? "Final" : "Listening…"}</span></div><p>{entry.text}</p></article>)}
      </div>
      {!following && <button className="audio-refresh" onClick={() => { follow.current = true; setFollowing(true); if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight; }}>Follow latest</button>}
      {!!snapshot?.trimmed && <p className="transcript-footnote">Showing recent conversation. Older entries are discarded to keep memory bounded.</p>}
      <p className="transcript-footnote">Live text stays in memory for this session. A new session or sign-out clears it.</p>
    </section>
    <LiveCue sessionId={snapshot?.sessionId ?? 0} active={authenticated && !!snapshot?.understanding.active} />
  </div>;
}
function streamLabel(state: string) {
  return ({ streaming: "Listening", connecting: "Connecting", reconnecting: "Reconnecting", renewing: "Reconnecting", stopped: "Stopped", idle: "Not started", error: "Interrupted" } as Record<string, string>)[state] || "Checking connection";
}
function friendlyTranscriptionMessage(message: string) {
  if (/api.key|not.configured|configure|DEEPGRAM_API_KEY|GEMINI_API_KEY/i.test(message)) return "Live transcription is unavailable. Check your MeetGuide service configuration, then try a new session.";
  if (/quota|rate.limit/i.test(message)) return "The transcription service is temporarily busy. Try a new session shortly.";
  if (/Gemini|Deepgram|OpenAI|WebSocket/i.test(message)) return "The transcription connection was interrupted. If it does not recover, stop and restart the session.";
  return message;
}
