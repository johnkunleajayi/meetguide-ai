import { AudioConfiguration, LevelMeter } from "./AudioConfiguration";
import { PrivateDisplay } from "./PrivateDisplay";
import { DesktopIcon } from "./DesktopIcon";
import { PreparationPicker } from "./PreparationPicker";
import type { Preparation } from "../lib/preparation";
import { TranscriptPanel } from "./TranscriptPanel";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAudioCapture } from "../hooks/useAudioCapture";
import { listAudioDevices, type AudioDevice, type AudioDevices, type AudioMode } from "../lib/audio";

export function AudioSession({ authenticated, onBusyChange }: { authenticated: boolean; onBusyChange?: (value: boolean) => void }) {
  const { status, pending, error, start, stop } = useAudioCapture(authenticated);
  const [preparation, setPreparation] = useState<Preparation | null>(null);
  const [mode, setMode] = useState<AudioMode>("system");
  const [devices, setDevices] = useState<AudioDevices>({ system: [], microphones: [] });
  const [system, setSystem] = useState("");
  const [microphone, setMicrophone] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const controlbar = useRef<HTMLElement>(null);
  const listening = status.state === "listening";
  const locked = !!pending || listening;
  useEffect(() => {
    if (listening) controlbar.current?.scrollIntoView?.({ block: "start", behavior: "instant" });
  }, [listening]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setDeviceError(null);
    try {
      const next = await listAudioDevices();
      setDevices(next);
      setSystem((value) => next.system.some((device) => device.id === value) ? value : "");
      setMicrophone((value) => next.microphones.some((device) => device.id === value) ? value : "");
    } catch (reason) {
      setDevices({ system: [], microphones: [] });
      setDeviceError(typeof reason === "string" ? reason : "Unable to list audio devices. Check Windows Sound settings and retry.");
    } finally { setRefreshing(false); }
  }, []);

  useEffect(() => { if (authenticated) void refresh(); }, [authenticated, refresh]);
  useEffect(() => { onBusyChange?.(!!pending); }, [pending, onBusyChange]);
  const hasSystem = mode !== "microphone";
  const hasMicrophone = mode !== "system";
  const available = (items: AudioDevice[], chosen: string) => items.some((device) => chosen ? device.id === chosen : device.isDefault);
  const missingSystem = hasSystem && !available(devices.system, system);
  const missingMicrophone = hasMicrophone && !available(devices.microphones, microphone);
  const canStart = authenticated && !!preparation && !locked && !refreshing && !missingSystem && !missingMicrophone;
  const label = pending === "starting" ? "Starting…" : pending === "stopping" ? "Stopping…" : listening ? "Listening" : status.state === "error" ? "Capture stopped" : !authenticated ? "Sign in to begin" : !preparation ? "Preparation needed" : missingSystem || missingMicrophone ? "Check audio" : "Ready";

  return <div className="session-workspace" data-live={locked} data-authenticated={authenticated}>
    <div className="session-heading"><p className="eyebrow">YOUR LIVE CONVERSATION COMPANION</p><h1>{locked ? "Your live conversation." : "Prepared. Present. Ready."}</h1><p>Confirm your preparation. Choose the voices to follow.</p></div>
    <div className="session-setup"><PreparationPicker authenticated={authenticated} locked={locked} value={preparation} onChange={setPreparation} /><AudioConfiguration {...{authenticated,locked,refreshing,mode,setMode,devices,system,setSystem,microphone,setMicrophone}} refresh={() => void refresh()} /></div>
    <PrivateDisplay />
    <section ref={controlbar} className="session-controlbar" aria-label="Desktop status"><div className="session-readiness"><span className={`status-dot${listening ? " is-listening" : ""}`} aria-hidden="true" /><div><span className="ready" role="status">{label}</span><p>{listening ? (mode === "both" ? "Following Them + You" : mode === "system" ? "Following Them" : "Following You") : !authenticated ? "Sign in to begin" : !preparation ? "Choose a preparation" : refreshing ? "Checking audio devices" : missingSystem || missingMicrophone ? "Check your audio devices" : "Your preparation and audio are set"}</p></div></div>
      {listening || pending === "stopping" ? <button className="start-session audio-stop" disabled={!!pending} onClick={() => { void stop(); }}><DesktopIcon name="stop" size={15} />Stop Session</button> : <button className="start-session" disabled={!canStart} onClick={() => { if (preparation) void start({ mode, systemDeviceId: system || null, microphoneDeviceId: microphone || null }, preparation.id, preparation.updated_at); }}>Start Session<DesktopIcon name="arrow" size={17} /></button>}
    </section>
    <div className="session-feedback">
      {authenticated && !locked && !refreshing && (missingSystem || missingMicrophone) && <p role="alert">{missingSystem ? "No selected/default playback device is available. " : ""}{missingMicrophone ? "No selected/default microphone is available. " : ""}Check Windows Sound settings, then refresh devices.</p>}
      {(error || deviceError) && <p role="alert">{error || deviceError}</p>}
    </div>
    {(status.system || status.microphone) && <details className="audio-activity"><summary><span><DesktopIcon name="audio" size={16} />Audio activity</span><DesktopIcon name="chevron" size={14} /></summary><div>{status.system && <LevelMeter label="System Audio" value={status.system} />}{status.microphone && <LevelMeter label="Microphone" value={status.microphone} />}</div></details>}
    <TranscriptPanel authenticated={authenticated} />
    <p className="audio-privacy">Audio is streamed for live transcription. MeetGuide does not save audio or transcripts.</p>
  </div>;
}
