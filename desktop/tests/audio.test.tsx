import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AudioSession } from "../src/components/AudioSession";
import * as audio from "../src/lib/audio";
vi.mock("../src/lib/audio", async (original) => ({ ...await original<typeof import("../src/lib/audio")>(), listAudioDevices: vi.fn(), startAudio: vi.fn(), stopAudio: vi.fn(), readAudioStatus: vi.fn() }));
const devices = { system: [{ id: "speakers", name: "Speakers", isDefault: true }], microphones: [{ id: "mic", name: "Mic", isDefault: true }] };
const meter = { deviceName: "Speakers", rms: 0.1, peak: 0.5, frames: 4800, sampleRate: 48000, channels: 2, discontinuities: 0 };
const listening: audio.CaptureStatus = { state: "listening", system: meter, microphone: null, error: null };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(audio.listAudioDevices).mockResolvedValue(devices);
  vi.mocked(audio.startAudio).mockResolvedValue(listening);
  vi.mocked(audio.stopAudio).mockResolvedValue();
  vi.mocked(audio.readAudioStatus).mockResolvedValue(listening);
});
afterEach(cleanup);
const start = () => screen.getByRole("button", { name: "Start Session" }) as HTMLButtonElement;
async function ready() { await waitFor(() => expect(start().disabled).toBe(false)); }
it("requires authentication before enumeration or capture", () => {
  render(<AudioSession authenticated={false} />);
  expect(start().disabled).toBe(true); fireEvent.click(start());
  expect(audio.startAudio).not.toHaveBeenCalled(); expect(audio.listAudioDevices).not.toHaveBeenCalled();
});
it("starts loopback, shows RMS activity, stops and restarts", async () => {
  render(<AudioSession authenticated />); await ready();
  const button = start(); fireEvent.click(button); fireEvent.click(button);
  await screen.findByText("Listening"); expect(audio.startAudio).toHaveBeenCalledOnce();
  expect(audio.startAudio).toHaveBeenCalledWith({ mode: "system", systemDeviceId: null, microphoneDeviceId: null });
  expect(Number(screen.getByRole("meter", { name: "System Audio activity" }).getAttribute("value"))).toBeCloseTo(66.6667, 3);
  fireEvent.click(screen.getByText("Stop Session")); await ready(); expect(screen.queryByRole("meter")).toBeNull();
  fireEvent.click(start()); await screen.findByText("Listening"); expect(audio.startAudio).toHaveBeenCalledTimes(2);
});
it("supports both streams and selected devices", async () => {
  vi.mocked(audio.startAudio).mockResolvedValue({ ...listening, microphone: meter });
  render(<AudioSession authenticated />); await ready();
  fireEvent.change(screen.getByLabelText("Audio source"), { target: { value: "both" } });
  fireEvent.change(screen.getByLabelText("Playback device"), { target: { value: "speakers" } });
  fireEvent.change(screen.getByLabelText("Microphone device"), { target: { value: "mic" } });
  fireEvent.click(start()); await screen.findByText("Listening");
  expect(audio.startAudio).toHaveBeenCalledWith({ mode: "both", systemDeviceId: "speakers", microphoneDeviceId: "mic" });
  expect(screen.getByRole("meter", { name: "Microphone activity" })).toBeTruthy();
});
it("supports microphone only", async () => {
  vi.mocked(audio.startAudio).mockResolvedValue({ ...listening, system: null, microphone: meter });
  render(<AudioSession authenticated />); await ready();
  fireEvent.change(screen.getByLabelText("Audio source"), { target: { value: "microphone" } });
  expect(screen.queryByLabelText("Playback device")).toBeNull(); fireEvent.click(start()); await screen.findByText("Listening");
  expect(audio.startAudio).toHaveBeenCalledWith({ mode: "microphone", systemDeviceId: null, microphoneDeviceId: null });
});
it("handles missing microphone and refresh recovery", async () => {
  vi.mocked(audio.listAudioDevices).mockResolvedValueOnce({ ...devices, microphones: [] });
  render(<AudioSession authenticated />); await ready();
  fireEvent.change(screen.getByLabelText("Audio source"), { target: { value: "both" } });
  expect(start().disabled).toBe(true); expect(screen.getByRole("alert").textContent).toContain("microphone");
  fireEvent.click(screen.getByText("Refresh devices")); await ready();
});
it("reports unavailable playback devices", async () => {
  vi.mocked(audio.listAudioDevices).mockResolvedValue({ ...devices, system: [] });
  render(<AudioSession authenticated />);
  expect((await screen.findByRole("alert")).textContent).toContain("playback"); expect(start().disabled).toBe(true);
});
it("reports startup failure without claiming to listen", async () => {
  vi.mocked(audio.startAudio).mockRejectedValue("Microphone access is disabled in Windows.");
  render(<AudioSession authenticated />); await ready(); fireEvent.click(start());
  expect((await screen.findByRole("alert")).textContent).toContain("Microphone access"); expect(screen.queryByText("Listening")).toBeNull(); await ready();
});
it("reports device loss from native polling", async () => {
  vi.mocked(audio.readAudioStatus).mockResolvedValue({ state: "error", system: null, microphone: null, error: "Audio device changed. Refresh and restart." });
  render(<AudioSession authenticated />); await ready(); fireEvent.click(start());
  expect((await screen.findByRole("alert")).textContent).toContain("Audio device changed"); await ready();
});
it("stops after authentication is removed", async () => {
  const { rerender } = render(<AudioSession authenticated />); await ready(); fireEvent.click(start()); await screen.findByText("Listening");
  rerender(<AudioSession authenticated={false} />); await waitFor(() => expect(audio.stopAudio).toHaveBeenCalledOnce());
  await waitFor(() => expect(start().disabled).toBe(true));
});
it("keeps Stop Session available after stop failure", async () => {
  vi.mocked(audio.stopAudio).mockRejectedValue("IPC failure");
  render(<AudioSession authenticated />); await ready(); fireEvent.click(start()); await screen.findByText("Listening"); fireEvent.click(screen.getByText("Stop Session"));
  expect((await screen.findByRole("alert")).textContent).toContain("Unable to stop capture");
  expect((screen.getByRole("button", { name: "Stop Session" }) as HTMLButtonElement).disabled).toBe(false);
});
it("bounds invalid and silent meter values", () => {
  expect(audio.meterPercent(Number.NaN)).toBe(0); expect(audio.meterPercent(0)).toBe(0);
  expect(audio.meterPercent(2)).toBe(100); expect(audio.meterPercent(0.001)).toBeCloseTo(0);
});

it("keeps Stop visible if authentication disappears during startup and cleanup fails", async () => {
  let finish!: (status: audio.CaptureStatus) => void;
  vi.mocked(audio.startAudio).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  vi.mocked(audio.stopAudio).mockRejectedValue("IPC failure");
  const { rerender } = render(<AudioSession authenticated />); await ready(); fireEvent.click(start());
  rerender(<AudioSession authenticated={false} />);
  finish(listening);
  expect((await screen.findByRole("alert")).textContent).toContain("Unable to stop capture");
  expect((screen.getByRole("button", { name: "Stop Session" }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByRole("button", { name: "Start Session" })).toBeNull();
});
