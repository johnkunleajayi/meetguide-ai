import { useEffect, useRef, useState } from "react";
import { idleStatus, readAudioStatus, startAudio, stopAudio, type CaptureOptions } from "../lib/audio";

export function useAudioCapture(authenticated: boolean) {
  const [status, setStatus] = useState(idleStatus);
  const [pending, setPending] = useState<"starting" | "stopping" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const enabled = useRef(authenticated);
  enabled.current = authenticated;

  useEffect(() => {
    if (status.state !== "listening" || pending) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await readAudioStatus();
        if (active && !busy.current) { setStatus(value); setError(value.error); }
      } catch {
        if (active) setError("Unable to read audio activity. Stop the session or close MeetGuide if this continues.");
      }
      if (active) timer = setTimeout(() => { void poll(); }, 100);
    }
    timer = setTimeout(() => { void poll(); }, 100);
    return () => { active = false; clearTimeout(timer); };
  }, [status.state, pending]);

  async function stop() {
    if (busy.current) return;
    busy.current = true;
    setPending("stopping");
    try {
      await stopAudio();
      setStatus(idleStatus());
      setError(null);
    } catch {
      setError("Unable to stop capture. Retry Stop Session or close MeetGuide to release audio devices.");
    } finally { busy.current = false; setPending(null); }
  }

  useEffect(() => {
    if (!authenticated && status.state === "listening") void stop();
  }, [authenticated, status.state]);

  async function start(options: CaptureOptions, preparationId: string, preparationRevision: string) {
    if (!enabled.current || busy.current) return;
    busy.current = true;
    setPending("starting");
    setError(null);
    try {
      const value = await startAudio(options, preparationId, preparationRevision);
      setStatus(value);
      if (!enabled.current) {
        try {
          await stopAudio();
          setStatus(idleStatus());
        } catch {
          // Keep the live state and Stop control if capture started during logout.
          setError("Unable to stop capture. Retry Stop Session or close MeetGuide to release audio devices.");
        }
      } else { setError(value.error); }
    } catch (reason) {
      setStatus(idleStatus());
      setError(typeof reason === "string" ? reason : "Unable to start audio capture. Check your audio devices and retry.");
    } finally { busy.current = false; setPending(null); }
  }

  return { status, pending, error, start, stop };
}

