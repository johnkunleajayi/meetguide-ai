import { useCallback, useEffect, useRef, useState } from "react";
import {
  privateDisplayAvailable, readPrivateDisplay, setPrivateDisplay, subscribePrivateDisplay,
  type PrivateDisplayStatus,
} from "../lib/privateDisplay";

export function PrivateDisplay() {
  const [status, setStatus] = useState<PrivateDisplayStatus | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(false);
  const revision = useRef(-1);
  const receive = useCallback((value: PrivateDisplayStatus) => {
    if (!mounted.current || value.revision < revision.current) return;
    revision.current = value.revision;
    setStatus(value);
    setError(null);
  }, []);

  useEffect(() => {
    mounted.current = true;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    if (!privateDisplayAvailable()) {
      receive({ state: "unsupported", requestedEnabled: true, revision: 0,
        message: "Private Display requires the Windows desktop application." });
      return () => { mounted.current = false; };
    }
    async function connect() {
      try {
        const cleanup = await subscribePrivateDisplay(value => { if (!disposed) receive(value); });
        if (disposed) { cleanup(); return; }
        unlisten = cleanup;
        const before = revision.current;
        try { receive(await readPrivateDisplay()); }
        catch { if (!disposed && revision.current === before) setError("Unable to verify Private Display. Check status before sharing."); }
      } catch {
        if (!disposed) setError("Unable to connect to Private Display status. Check status before sharing.");
      }
    }
    void connect();
    return () => { disposed = true; mounted.current = false; unlisten?.(); };
  }, [receive]);

  async function change(enabled?: boolean) {
    if (pending) return;
    setPending(true);
    const before = revision.current;
    try { receive(await (enabled === undefined ? readPrivateDisplay() : setPrivateDisplay(enabled))); }
    catch {
      if (mounted.current && revision.current === before) {
        setError("Unable to confirm Private Display. Check status or try again before sharing.");
      }
    } finally { if (mounted.current) setPending(false); }
  }

  const unsupported = status?.state === "unsupported";
  const label = error ? "Unverified" : status ? {
    on: "ON", off: "OFF", limited: "Limited", unknown: "Unverified", unsupported: "Unavailable",
  }[status.state] : "Checking…";
  const turnOff = status?.state === "on" || status?.state === "limited"
    || ((status?.state === "unknown" || !!error) && !!status?.requestedEnabled);

  return <section className="private-display" aria-label="Private Display">
    <div className="private-display-row">
      <strong role="status" aria-live="polite">Private Display: {label}</strong>
      <div className="private-display-actions">
        <button type="button" disabled={pending || !status || unsupported}
          aria-label={`Turn ${turnOff ? "off" : "on"} Private Display`}
          onClick={() => { void change(!turnOff); }}>{pending ? "Checking…" : turnOff ? "Turn off" : "Turn on"}</button>
        {!unsupported && <button type="button" disabled={pending}
          onClick={() => { void change(); }}>Check status</button>}
      </div>
    </div>
    {(error || status?.message) && <p role="status">{error || status?.message}</p>}
    <p>Excludes this window from supported Windows captures. Screen-sharing tools may vary; verify before sharing.</p>
  </section>;
}
