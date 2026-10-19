import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TranscriptPanel } from "../src/components/TranscriptPanel";
import { readTranscript, type TranscriptSnapshot } from "../src/lib/transcription";
vi.mock("../src/lib/cue", () => ({ prepareCue: vi.fn(), readCue: vi.fn(async () => ({ sessionId: 0, eventId: 0, status: "idle", answer: null, grounding: null, sourceCount: 0, error: null })) }));
vi.mock("../src/lib/transcription", async (original) => ({ ...await original<typeof import("../src/lib/transcription")>(), readTranscript: vi.fn() }));
const partial: TranscriptSnapshot = { version: 1, sessionId: 1, entries: [{ id: 1, source: "system", text: "Interim words", finalText: false, interrupted: false, offsetMs: 0 }], streams: [{ source: "system", state: "streaming", message: null, droppedChunks: 0 }], trimmed: 0, understanding: { active: true, turns: [], events: [], trimmedTurns: 0 } };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(readTranscript).mockResolvedValue(null); });
afterEach(cleanup);
it("does not poll or expose transcript content when signed out", () => {
  render(<TranscriptPanel authenticated={false} />);
  expect(readTranscript).not.toHaveBeenCalled();
  expect(screen.queryByText("Interim words")).toBeNull();
});
it("updates partial text in place, finalizes, and preserves Them/You labels", async () => {
  vi.mocked(readTranscript).mockResolvedValueOnce(partial).mockResolvedValue({ ...partial, version: 2, entries: [
    { ...partial.entries[0], text: "Final words.", finalText: true },
    { id: 2, source: "microphone", text: "My reply.", finalText: true, interrupted: false, offsetMs: 100 },
  ] });
  render(<TranscriptPanel authenticated />);
  expect(await screen.findByText("Interim words")).toBeTruthy();
  expect(await screen.findByText("Final words.")).toBeTruthy();
  expect(screen.queryByText("Interim words")).toBeNull();
  expect(screen.getByText("My reply.")).toBeTruthy();
  expect(screen.getByText("Them")).toBeTruthy(); expect(screen.getByText("You")).toBeTruthy();
  expect(screen.getAllByRole("article").length).toBe(2);
});
it("surfaces configuration/provider failures independently of audio capture", async () => {
  vi.mocked(readTranscript).mockResolvedValue({ ...partial, entries: [], streams: [{ source: "system", state: "error", message: "Set DEEPGRAM_API_KEY on the backend and restart the API.", droppedChunks: 0 }] });
  render(<TranscriptPanel authenticated />);
  expect((await screen.findByRole("alert")).textContent).toContain("DEEPGRAM_API_KEY");
});
it("pauses following while reading older text and offers Follow latest", async () => {
  vi.mocked(readTranscript).mockResolvedValue(partial);
  render(<TranscriptPanel authenticated />); await screen.findByText("Interim words");
  const scroller = screen.getByLabelText("Conversation transcript");
  Object.defineProperty(scroller, "scrollHeight", { configurable: true, value: 1000 });
  Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 100 });
  scroller.scrollTop = 0; fireEvent.scroll(scroller);
  fireEvent.click(screen.getByText("Follow latest"));
  expect(scroller.scrollTop).toBe(1000);
  expect(screen.queryByText("Follow latest")).toBeNull();
});
it("clears transcript visibility on logout and cancels polling", async () => {
  vi.mocked(readTranscript).mockResolvedValue(partial);
  const { rerender, unmount } = render(<TranscriptPanel authenticated />);
  await screen.findByText("Interim words"); rerender(<TranscriptPanel authenticated={false} />);
  expect(screen.queryByText("Interim words")).toBeNull(); unmount();
  const count = vi.mocked(readTranscript).mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 250));
  expect(readTranscript).toHaveBeenCalledTimes(count);
});
it("a new capture session replaces the previous transcript", async () => {
  vi.mocked(readTranscript).mockResolvedValueOnce(partial).mockResolvedValue({ ...partial, version: 3, sessionId: 2, entries: [] });
  render(<TranscriptPanel authenticated />); await screen.findByText("Interim words");
  await waitFor(() => expect(screen.queryByText("Interim words")).toBeNull());
});

const detected: TranscriptSnapshot = { ...partial, understanding: { active: true, turns: [], trimmedTurns: 0, events: [{ id: 1, type: "question", speaker: "them", text: "How did you handle the migration?", confidence: 0.94, turnId: 1, detectedAtMs: 1200, context: [] }] } };
it("shows a small question indication and clears it on logout", async () => {
  vi.mocked(readTranscript).mockResolvedValue(detected);
  const { rerender } = render(<TranscriptPanel authenticated />);
  expect((await screen.findByRole("status")).textContent).toContain("Question detected");
  expect(screen.getAllByText("How did you handle the migration?")[0]).toBeTruthy();
  rerender(<TranscriptPanel authenticated={false} />);
  expect(screen.queryByRole("status")).toBeNull();
});
it("clears detected questions on a new session", async () => {
  vi.mocked(readTranscript).mockResolvedValueOnce(detected).mockResolvedValue({ ...partial, sessionId: 2, version: 3 });
  render(<TranscriptPanel authenticated />); await screen.findByRole("status");
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
});
it("does not expose reserved opportunity events or questions from You", async () => {
  vi.mocked(readTranscript).mockResolvedValue({ ...detected, understanding: { ...detected.understanding, events: [
    { ...detected.understanding.events[0], type: "important_point" },
    { ...detected.understanding.events[0], id: 2, speaker: "you" },
  ] } });
  render(<TranscriptPanel authenticated />); await screen.findByText("Interim words");
  expect(screen.queryByRole("status")).toBeNull();
});
