import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LiveCue } from "../src/components/LiveCue";
import { clearCue, prepareCue, readCue, type CueSnapshot } from "../src/lib/cue";
import type { MeaningfulEvent } from "../src/lib/understanding";
vi.mock("../src/lib/cue", () => ({ clearCue: vi.fn(), prepareCue: vi.fn(), readCue: vi.fn() }));
const question: MeaningfulEvent = { id: 1, type: "question", speaker: "them", text: "How did you handle the integration?", confidence: 0.94, turnId: 1, detectedAtMs: 1200, context: [] };
const answer = "I developed Salesforce integrations with external APIs.\n\nI would build on that approach by checking the requirements carefully.";
const ready: CueSnapshot = { sessionId: 1, eventId: 1, status: "ready", answer, grounding: "document_supported", sourceCount: 1, error: null };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(prepareCue).mockResolvedValue(); vi.mocked(clearCue).mockResolvedValue(); vi.mocked(readCue).mockResolvedValue(ready); });
afterEach(cleanup);

it("triggers from a confident question and renders ready-to-speak paragraphs", async () => {
  render(<LiveCue sessionId={1} event={question} active />);
  expect(screen.getByText("Preparing answer…")).toBeTruthy();
  expect(await screen.findByText("I developed Salesforce integrations with external APIs.")).toBeTruthy();
  expect(screen.getByText("I would build on that approach by checking the requirements carefully.")).toBeTruthy();
  expect(screen.getByText("Uses 1 document excerpt")).toBeTruthy();
  expect(prepareCue).toHaveBeenCalledWith(1, 1, false);
  expect(screen.queryByRole("list")).toBeNull();
});
it("does not trigger for nonquestions, You, low confidence or an inactive session", () => {
  const { rerender } = render(<LiveCue sessionId={1} event={{ ...question, type: "important_point" }} active />);
  rerender(<LiveCue sessionId={1} event={{ ...question, speaker: "you" }} active />);
  rerender(<LiveCue sessionId={1} event={{ ...question, confidence: 0.5 }} active />);
  rerender(<LiveCue sessionId={1} event={question} active={false} />);
  expect(prepareCue).not.toHaveBeenCalled(); expect(screen.queryByLabelText("Live Cue")).toBeNull();
});
it("repeated snapshots of the same event do not retrigger generation", async () => {
  const { rerender } = render(<LiveCue sessionId={1} event={question} active />);
  await screen.findByText("Ready to speak");
  rerender(<LiveCue sessionId={1} event={{ ...question, context: [] }} active />);
  expect(prepareCue).toHaveBeenCalledTimes(1);
});
it("new question hides the previous cue immediately and ignores stale polled results", async () => {
  const { rerender } = render(<LiveCue sessionId={1} event={question} active />);
  await screen.findByText("Ready to speak");
  rerender(<LiveCue sessionId={1} event={{ ...question, id: 2, text: "What was the biggest challenge?" }} active />);
  expect(screen.queryByText("I developed Salesforce integrations with external APIs.")).toBeNull();
  await waitFor(() => expect(prepareCue).toHaveBeenCalledWith(1, 2, false));
  expect(screen.getByText("Preparing answer…")).toBeTruthy();
  expect(screen.queryByText("I developed Salesforce integrations with external APIs.")).toBeNull();
});
it("ignores a late response from an older poll after supersession", async () => {
  let finish!: (value: CueSnapshot) => void;
  vi.mocked(readCue).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const { rerender } = render(<LiveCue sessionId={1} event={question} active />);
  await waitFor(() => expect(readCue).toHaveBeenCalledTimes(1));
  vi.mocked(readCue).mockResolvedValue({ ...ready, eventId: 2, answer: "I'd focus on the current question.\n\nI'd keep the answer concise." });
  rerender(<LiveCue sessionId={1} event={{ ...question, id: 2 }} active />);
  await screen.findByText("I'd focus on the current question.");
  finish(ready);
  await waitFor(() => expect(screen.queryByText("I developed Salesforce integrations with external APIs.")).toBeNull());
});
it("surfaces provider failure and explicitly retries", async () => {
  vi.mocked(readCue).mockResolvedValue({ ...ready, status: "error", answer: null, error: "Unable to prepare a grounded answer. Please retry." });
  render(<LiveCue sessionId={1} event={question} active />);
  await screen.findByRole("alert");
  vi.mocked(readCue).mockResolvedValue(ready);
  fireEvent.click(screen.getByText("Retry answer"));
  await screen.findByText("Ready to speak");
  expect(prepareCue).toHaveBeenLastCalledWith(1, 1, true);
});
it("clears cues on stop/logout and starts fresh after restart", async () => {
  const { rerender } = render(<LiveCue sessionId={1} event={question} active />);
  await screen.findByText("Ready to speak");
  rerender(<LiveCue sessionId={1} event={question} active={false} />);
  expect(screen.queryByLabelText("Live Cue")).toBeNull();
  vi.mocked(readCue).mockResolvedValue({ ...ready, sessionId: 2 });
  rerender(<LiveCue sessionId={2} event={question} active />);
  expect(screen.queryByText("I developed Salesforce integrations with external APIs.")).toBeNull();
  await screen.findByText("Ready to speak");
  expect(prepareCue).toHaveBeenLastCalledWith(2, 1, false);
  rerender(<LiveCue sessionId={0} active={false} />);
  expect(screen.queryByLabelText("Live Cue")).toBeNull();
});
it("labels the no-context answer as a general approach", async () => {
  vi.mocked(readCue).mockResolvedValue({ ...ready, grounding: "general_approach", sourceCount: 0 });
  render(<LiveCue sessionId={1} event={question} active />);
  expect(await screen.findByText("General approach · No personal experience claimed")).toBeTruthy();
});

it("Clear dismisses the answer and question without replaying it; the next question still runs", async () => {
  const onClear = vi.fn();
  const { rerender } = render(<LiveCue sessionId={1} event={question} active onClear={onClear} />);
  await screen.findByText("Ready to speak");
  fireEvent.click(screen.getByRole("button", { name: "Clear Live Cue" }));
  await screen.findByText("Listening for the next question.");
  expect(screen.queryByText(question.text)).toBeNull();
  expect(screen.queryByText("I developed Salesforce integrations with external APIs.")).toBeNull();
  expect(clearCue).toHaveBeenCalledWith(1, 1);
  expect(onClear).toHaveBeenCalledWith(1, 1);
  rerender(<LiveCue sessionId={1} event={{ ...question }} active onClear={onClear} />);
  expect(prepareCue).toHaveBeenCalledTimes(1);
  vi.mocked(readCue).mockResolvedValue({ ...ready, eventId: 2 });
  rerender(<LiveCue sessionId={1} event={{ ...question, id: 2 }} active onClear={onClear} />);
  await screen.findByText("Ready to speak");
  expect(prepareCue).toHaveBeenLastCalledWith(1, 2, false);
});
it("Clear during preparation ignores a late poll and reports clear failure safely", async () => {
  let resolve!: (value: CueSnapshot) => void;
  vi.mocked(readCue).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  render(<LiveCue sessionId={1} event={question} active />);
  await waitFor(() => expect(readCue).toHaveBeenCalled());
  vi.mocked(clearCue).mockRejectedValueOnce(new Error("native failure"));
  fireEvent.click(screen.getByRole("button", { name: "Clear Live Cue" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Please retry Clear");
  fireEvent.click(screen.getByRole("button", { name: "Clear Live Cue" }));
  await screen.findByText("Listening for the next question.");
  resolve(ready);
  await waitFor(() => expect(screen.queryByText("Ready to speak")).toBeNull());
});
