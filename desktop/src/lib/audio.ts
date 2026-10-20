import { invoke } from "@tauri-apps/api/core";
export type AudioMode = "system" | "microphone" | "both";
export interface AudioDevice { id: string; name: string; isDefault: boolean }
export interface AudioDevices { system: AudioDevice[]; microphones: AudioDevice[] }
export interface StreamMeter { deviceName: string; rms: number; peak: number; frames: number; sampleRate: number; channels: number; discontinuities: number }
export interface CaptureStatus { state: "idle" | "starting" | "listening" | "error"; system: StreamMeter | null; microphone: StreamMeter | null; error: string | null }
export interface CaptureOptions { mode: AudioMode; systemDeviceId: string | null; microphoneDeviceId: string | null }
export const idleStatus = (): CaptureStatus => ({ state: "idle", system: null, microphone: null, error: null });
export const listAudioDevices = () => invoke<AudioDevices>("audio_devices");
export const startAudio = (options: CaptureOptions, preparationId: string, preparationRevision: string) => invoke<CaptureStatus>("audio_start", { options, preparationId, preparationRevision });
export const stopAudio = () => invoke<void>("audio_stop");
export const readAudioStatus = () => invoke<CaptureStatus>("audio_status");
export function meterPercent(rms: number) {
  if (!Number.isFinite(rms) || rms <= 0) return 0;
  return Math.max(0, Math.min(100, (20 * Math.log10(rms) + 60) / 60 * 100));
}
