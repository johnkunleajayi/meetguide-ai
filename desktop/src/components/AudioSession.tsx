import { PreparationPicker } from "./PreparationPicker";
import type { Preparation } from "../lib/preparation";
import { TranscriptPanel } from "./TranscriptPanel";
import { useCallback, useEffect, useState } from "react";
import { useAudioCapture } from "../hooks/useAudioCapture";
import { listAudioDevices, meterPercent, type AudioDevice, type AudioDevices, type AudioMode, type StreamMeter } from "../lib/audio";

function LevelMeter({ label, value }: { label: string; value: StreamMeter }) {
  const percent = meterPercent(value.rms);
  return <div className="audio-level">
    <div className="audio-level-label"><span>{label}</span><span>{value.rms > 0.001 ? "Audio detected" : "Quiet / waiting for audio"}</span></div>
    <meter min={0} max={100} value={percent} aria-label={`${label} activity`}>{Math.round(percent)}%</meter>
    <p className="audio-device-name" title={value.deviceName}>{value.deviceName} · {value.sampleRate.toLocaleString()} Hz · {value.channels} ch</p>
  </div>;
}

function DeviceSelect({ label, devices, value, setValue, disabled }: { label: string; devices: AudioDevice[]; value: string; setValue: (value: string) => void; disabled: boolean }) {
  const defaultDevice = devices.find((device) => device.isDefault);
  return <label className="audio-field">{label}
    <select value={value} onChange={(event) => setValue(event.target.value)} disabled={disabled}>
      <option value="">Windows default{defaultDevice ? ` — ${defaultDevice.name}` : " (not available)"}</option>
      {devices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}
    </select>
  </label>;
}

export function AudioSession({ authenticated, onBusyChange }: { authenticated: boolean; onBusyChange?: (value: boolean) => void }) {
  const { status, pending, error, start, stop } = useAudioCapture(authenticated);
  const [preparation, setPreparation] = useState<Preparation | null>(null);
  const [mode, setMode] = useState<AudioMode>("system");
  const [devices, setDevices] = useState<AudioDevices>({ system: [], microphones: [] });
  const [system, setSystem] = useState("");
  const [microphone, setMicrophone] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const listening = status.state === "listening";
  const locked = !!pending || listening;

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
  const label = pending === "starting" ? "Starting…" : pending === "stopping" ? "Stopping…" : listening ? "Listening" : status.state === "error" ? "Capture stopped" : "Ready";

  return <><PreparationPicker authenticated={authenticated} locked={locked} value={preparation} onChange={setPreparation} /><section className="status-panel" aria-label="Desktop status">
    <div className="status-row">
      <span className="status-label">Application status</span>
      <span className="ready" role="status"><span className={`status-dot${listening ? " is-listening" : ""}`} aria-hidden="true" />{label}</span>
    </div>
    <div className="session-action">
      <fieldset className="audio-options" disabled={!authenticated || locked || refreshing}>
        <legend>Audio source</legend>
        <select aria-label="Audio source" value={mode} onChange={(event) => setMode(event.target.value as AudioMode)}>
          <option value="system">System Audio</option><option value="microphone">Microphone</option><option value="both">Both</option>
        </select>
        {hasSystem && <DeviceSelect label="Playback device" devices={devices.system} value={system} setValue={setSystem} disabled={locked} />}
        {hasMicrophone && <DeviceSelect label="Microphone device" devices={devices.microphones} value={microphone} setValue={setMicrophone} disabled={locked} />}
      </fieldset>
      {authenticated && !locked && <button className="audio-refresh" onClick={() => { void refresh(); }} disabled={refreshing}>{refreshing ? "Refreshing devices…" : "Refresh devices"}</button>}
      {status.system && <LevelMeter label="System Audio" value={status.system} />}
      {status.microphone && <LevelMeter label="Microphone" value={status.microphone} />}
      {listening || pending === "stopping" ?
        <button className="start-session audio-stop" disabled={!!pending} onClick={() => { void stop(); }}>Stop Session</button> :
        <button className="start-session" disabled={!canStart} onClick={() => { if (preparation) void start({ mode, systemDeviceId: system || null, microphoneDeviceId: microphone || null }, preparation.id, preparation.updated_at); }}>Start Session</button>}
      {!authenticated && <p>Sign in to start a session.</p>}
      {authenticated && !locked && !refreshing && (missingSystem || missingMicrophone) && <p role="alert">{missingSystem ? "No selected/default playback device is available. " : ""}{missingMicrophone ? "No selected/default microphone is available. " : ""}Check Windows Sound settings, then refresh devices.</p>}
      {(error || deviceError) && <p role="alert">{error || deviceError}</p>}
      <p className="audio-privacy">Audio is streamed for live transcription. MeetGuide does not save audio or transcripts.</p>
    </div>
  </section><TranscriptPanel authenticated={authenticated} /></>;
}
