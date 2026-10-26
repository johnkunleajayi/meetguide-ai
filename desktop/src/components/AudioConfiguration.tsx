import type { AudioDevice, AudioDevices, AudioMode, StreamMeter } from "../lib/audio";
import { meterPercent } from "../lib/audio";
import { DesktopIcon } from "./DesktopIcon";
const modes = [
  { id: "system", name: "System Audio", description: "Them", icon: "speaker" },
  { id: "microphone", name: "Microphone", description: "You", icon: "mic" },
  { id: "both", name: "Both", description: "Them + You", icon: "both" },
] as const;
function DeviceSelect({ label, devices, value, setValue, disabled }: { label: string; devices: AudioDevice[]; value: string; setValue: (value: string) => void; disabled: boolean }) {
  const defaultDevice = devices.find(device => device.isDefault);
  return <label className="audio-field">{label}<select value={value} onChange={event => setValue(event.target.value)} disabled={disabled}><option value="">Windows default{defaultDevice ? ` — ${defaultDevice.name}` : " (not available)"}</option>{devices.map(device => <option key={device.id} value={device.id}>{device.name}</option>)}</select></label>;
}
interface Props { authenticated: boolean; locked: boolean; refreshing: boolean; mode: AudioMode; setMode: (mode: AudioMode) => void; devices: AudioDevices; system: string; setSystem: (id: string) => void; microphone: string; setMicrophone: (id: string) => void; refresh: () => void }
export function AudioConfiguration({ authenticated, locked, refreshing, mode, setMode, devices, system, setSystem, microphone, setMicrophone, refresh }: Props) {
  return <section className="audio-configuration" aria-label="Audio configuration"><div className="setup-section-heading"><span>02 / AUDIO</span><h2>Follow the right voices.</h2></div>
    <fieldset className="audio-options" disabled={!authenticated || locked || refreshing}><legend>Audio source</legend><div className="audio-mode-options">{modes.map(item => <label key={item.id} data-selected={mode === item.id}><input type="radio" name="audio-source" aria-label={item.name} value={item.id} checked={mode === item.id} onChange={() => setMode(item.id)} /><DesktopIcon name={item.icon} /><strong>{item.name}</strong><span>{item.description}</span></label>)}</div></fieldset>
    <p className="audio-source-help">{mode === "both" ? "Both sides stay distinct: their audio is Them; your microphone is You." : mode === "system" ? "Follow the conversation playing through your computer." : "Follow your voice through the selected microphone."}</p>
    <details className="device-settings"><summary><span><DesktopIcon name="audio" size={16} />Devices</span><span>Playback & microphone<DesktopIcon name="chevron" size={14} /></span></summary><div className="device-settings-content">
      {mode !== "microphone" && <DeviceSelect label="Playback device" devices={devices.system} value={system} setValue={setSystem} disabled={locked || !authenticated || refreshing} />}
      {mode !== "system" && <DeviceSelect label="Microphone device" devices={devices.microphones} value={microphone} setValue={setMicrophone} disabled={locked || !authenticated || refreshing} />}
      {authenticated && !locked && <button className="audio-refresh" type="button" onClick={refresh} disabled={refreshing}><DesktopIcon name="refresh" size={14} />{refreshing ? "Refreshing devices…" : "Refresh devices"}</button>}
    </div></details>
  </section>;
}
export function LevelMeter({ label, value }: { label: string; value: StreamMeter }) {
  const percent = meterPercent(value.rms);
  return <div className="audio-level"><div className="audio-level-label"><strong>{label === "System Audio" ? "Them" : "You"}<span>{label}</span></strong><span>{value.rms > 0.001 ? "Audio detected" : "Quiet"}</span></div><meter min={0} max={100} value={percent} aria-label={`${label} activity`}>{Math.round(percent)}%</meter><p className="audio-device-name" title={value.deviceName}>{value.deviceName}</p></div>;
}
