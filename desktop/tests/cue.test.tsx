import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LiveCue } from "../src/components/LiveCue";
import { clearCue, prepareCue, readCue, subscribeCue, type CueCard, type CueSnapshot } from "../src/lib/cue";
vi.mock("../src/lib/cue", () => ({ clearCue: vi.fn(), prepareCue: vi.fn(), subscribeCue: vi.fn(), readCue: vi.fn() }));
const card = (id: number): CueCard => ({ id, question: `Question ${id}?`, status: "ready", answer: `I tested approach ${id}.\n\nI checked the result.`, grounding: "document_supported", sourceCount: 1, error: null });
const snapshot = (cards: CueCard[] = []): CueSnapshot => ({ sessionId: 1, cards, notice: null });
let updateCue: (snapshot: import("../src/lib/cue").CueSnapshot) => void = () => {};
const pushCue = (snapshot: import("../src/lib/cue").CueSnapshot) => act(() => updateCue(snapshot));
beforeEach(() => { vi.resetAllMocks(); vi.mocked(subscribeCue).mockImplementation(async callback => { updateCue = callback; return () => {}; }); vi.mocked(readCue).mockResolvedValue(snapshot()); vi.mocked(clearCue).mockResolvedValue(); vi.mocked(prepareCue).mockResolvedValue(); });
afterEach(cleanup);
it("renders chronological ready-to-speak cards without requiring Clear between questions", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1), card(2), card(3)]));
  render(<LiveCue sessionId={1} active />);
  await screen.findByText("I tested approach 3.");
  expect(screen.getAllByRole("article").map(node => node.getAttribute("aria-label"))).toEqual(["Cue 1", "Cue 2", "Cue 3"]);
  expect(screen.getAllByText("Uses 1 document excerpt")).toHaveLength(3);
  expect(prepareCue).not.toHaveBeenCalled();
});
it("retains every card without count pruning", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot(Array.from({ length: 40 }, (_, index) => card(index + 1))));
  render(<LiveCue sessionId={1} active />);
  await screen.findByText("I tested approach 40."); expect(screen.getAllByRole("article")).toHaveLength(40);
});
it("Remove deletes only the selected card and later cards continue arriving", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1), card(2), card(3)]));
  render(<LiveCue sessionId={1} active />); await screen.findByText("I tested approach 2.");
  fireEvent.click(screen.getByRole("button", { name: "Remove cue 2" }));
  await waitFor(() => expect(screen.queryByText("I tested approach 2.")).toBeNull());
  expect(clearCue).toHaveBeenCalledWith(1, 2); expect(screen.getByText("I tested approach 1.")).toBeTruthy(); expect(screen.getByText("I tested approach 3.")).toBeTruthy();
  pushCue(snapshot([card(1), card(3), card(4)]));
  await screen.findByText("I tested approach 4."); expect(screen.getAllByRole("article")).toHaveLength(3);
});
it("shows generating and queued questions independently while retaining completed cards", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1), { ...card(2), status: "generating", answer: null }, { ...card(3), status: "queued", answer: null }]));
  render(<LiveCue sessionId={1} active />); await screen.findByText("Queued");
  expect(screen.getByText("I tested approach 1.")).toBeTruthy(); expect(screen.getAllByText("Preparing answer…").length).toBeGreaterThan(0);
  expect(screen.queryByRole("button", { name: "Remove cue 2" })).toBeNull();
});
it("a failed answer can retry without removing other cues", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1), { ...card(2), status: "failed", answer: null, error: "Mock provider unavailable" }]));
  render(<LiveCue sessionId={1} active />); await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Retry answer" }));
  await waitFor(() => expect(prepareCue).toHaveBeenCalledWith(1, 2, true)); expect(screen.getByText("I tested approach 1.")).toBeTruthy();
});
it("clears the feed on stop/logout and does not restore cards on restart", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1)]));
  const { rerender } = render(<LiveCue sessionId={1} active />); await screen.findByText("I tested approach 1.");
  rerender(<LiveCue sessionId={1} active={false} />); expect(screen.queryByLabelText("Live Cue feed")).toBeNull();
  vi.mocked(readCue).mockResolvedValue({ sessionId: 2, cards: [], notice: null });
  rerender(<LiveCue sessionId={2} active />); expect(screen.queryByText("I tested approach 1.")).toBeNull(); await screen.findByText("Listening for the next question.");
});
it("a stale initial snapshot from the previous session cannot restore cue answers", async () => {
  let finish!: (value: CueSnapshot) => void;
  vi.mocked(readCue).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const { rerender } = render(<LiveCue sessionId={1} active />); await waitFor(() => expect(readCue).toHaveBeenCalled());
  rerender(<LiveCue sessionId={1} active={false} />); finish(snapshot([card(1)]));
  await waitFor(() => expect(screen.queryByText("I tested approach 1.")).toBeNull());
});
it("intent fallback notice does not hide the completed feed", async () => {
  vi.mocked(readCue).mockResolvedValue({ ...snapshot([card(1)]), notice: "Local question detection remains active." });
  render(<LiveCue sessionId={1} active />); await screen.findByText("Local question detection remains active."); expect(screen.getByText("I tested approach 1.")).toBeTruthy();
});
it("does not yank a reader away from older cards when a new cue arrives", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1)]));
  render(<LiveCue sessionId={1} active />); await screen.findByText("I tested approach 1.");
  const scroller = screen.getByLabelText("Session cue cards");
  Object.defineProperty(scroller, "scrollHeight", { configurable: true, value: 1000 }); Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 200 }); scroller.scrollTop = 0; fireEvent.scroll(scroller);
  pushCue(snapshot([card(1), card(2)]));
  await screen.findByText("I tested approach 2."); expect(scroller.scrollTop).toBe(0);
  fireEvent.click(await screen.findByRole("button", { name: "New cue · View latest" })); expect(scroller.scrollTop).toBe(1000);
});

it("a late Remove completion cannot hide a card in a fresh session", async () => {
  let finish!: () => void;
  vi.mocked(clearCue).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  vi.mocked(readCue).mockResolvedValue(snapshot([card(1)]));
  const { rerender } = render(<LiveCue sessionId={1} active />); await screen.findByText("I tested approach 1.");
  fireEvent.click(screen.getByRole("button", { name: "Remove cue 1" }));
  vi.mocked(readCue).mockResolvedValue({ sessionId: 2, notice: null, cards: [{ ...card(1), answer: "I am answering the fresh session question." }] });
  rerender(<LiveCue sessionId={2} active />); await screen.findByText("I am answering the fresh session question.");
  finish(); await waitFor(() => expect(screen.getByText("I am answering the fresh session question.")).toBeTruthy());
});
it("an existing completed answer remains readable during its related update", async () => {
  vi.mocked(readCue).mockResolvedValue(snapshot([{ ...card(1), status: "generating" }]));
  render(<LiveCue sessionId={1} active />); await screen.findByText("I tested approach 1.");
  expect(screen.getByRole("button", { name: "Remove cue 1" })).toBeTruthy();
});

it("logs only correlation and UI observation timing without private cue content", async () => {
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  try {
    vi.mocked(readCue).mockResolvedValue(snapshot([{ ...card(1), questionId: "q-ui-test", readyAtUnixMs: Date.now() - 20 }]));
    render(<LiveCue sessionId={1} active />);
    await screen.findByText("I tested approach 1.");
    await waitFor(() => expect(info).toHaveBeenCalled());
    const record = JSON.parse(info.mock.calls[0][1] as string);
    expect(record.stage).toBe("cue_ui_observed");
    expect(record.question_id).toBe("q-ui-test");
    expect(record.native_ready_to_ui_observed_ms).toBeGreaterThanOrEqual(0);
    expect(JSON.stringify(info.mock.calls)).not.toContain("I tested approach");
    expect(JSON.stringify(info.mock.calls)).not.toContain("Question 1");
  } finally { info.mockRestore(); }
});

it("updates the same card from responding draft to validated ready text using push", async () => {
 vi.mocked(readCue).mockResolvedValue(snapshot([{...card(1),status:"generating",answer:null}]));
 render(<LiveCue sessionId={1} active/>);await screen.findByText("Question 1?");
 pushCue(snapshot([{...card(1),status:"responding",grounding:null,answer:"I would clarify the goal."}]));
 expect(screen.getByText("Responding")).toBeTruthy();expect(screen.getByText("Draft · final grounding checks pending")).toBeTruthy();
 expect(screen.queryByText("Ready to speak")).toBeNull();expect(screen.getAllByRole("article")).toHaveLength(1);
 pushCue(snapshot([{...card(1),status:"responding",answer:"I would clarify the goal. Then test the plan."}]));
 expect(screen.getAllByRole("article")).toHaveLength(1);
 pushCue(snapshot([card(1)]));expect(screen.getByText("Ready to speak")).toBeTruthy();
 expect(screen.queryByText("Draft · final grounding checks pending")).toBeNull();
 expect(readCue).toHaveBeenCalledTimes(1);
});
it("clears a rejected partial, retries cleanly and can Remove while responding", async () => {
 vi.mocked(readCue).mockResolvedValue(snapshot([{...card(1),status:"responding",grounding:null,answer:"I would clarify the goal."},card(2)]));
 render(<LiveCue sessionId={1} active/>);await screen.findByText("I would clarify the goal.");
 pushCue(snapshot([{...card(1),status:"failed",answer:null,error:"Unable to prepare an answer."},card(2)]));
 expect(screen.queryByText("I would clarify the goal.")).toBeNull();fireEvent.click(screen.getByText("Retry answer"));
 await waitFor(()=>expect(prepareCue).toHaveBeenCalledWith(1,1,true));
 pushCue(snapshot([{...card(1),status:"responding",answer:"I would check a new plan."},card(2)]));
 fireEvent.click(screen.getByRole("button",{name:"Remove cue 1"}));await waitFor(()=>expect(screen.queryByText("I would check a new plan.")).toBeNull());
 expect(screen.getByText("I tested approach 2.")).toBeTruthy();
});

it("logs first visible draft timing per attempt without answer text and unsubscribes on cleanup",async()=>{
 const info=vi.spyOn(console,"info").mockImplementation(()=>{});const unlisten=vi.fn();
 vi.mocked(subscribeCue).mockImplementation(async callback=>{updateCue=callback;return unlisten;});
 vi.mocked(readCue).mockResolvedValue(snapshot([{...card(1),status:"responding",attempt:2,questionId:"q-first-output",firstOutputAtUnixMs:Date.now()-15,grounding:null,answer:"Private draft sentence."}]));
 try {
  const view=render(<LiveCue sessionId={1} active/>);await screen.findByText("Private draft sentence.");
  await waitFor(()=>expect(info).toHaveBeenCalled());
  const record=JSON.parse(info.mock.calls[0][1] as string);
  expect(record.stage).toBe("cue_first_output_ui_observed");expect(record.attempt).toBe(2);expect(record.native_first_output_to_ui_observed_ms).toBeGreaterThanOrEqual(0);
  expect(JSON.stringify(info.mock.calls)).not.toContain("Private draft sentence.");
  view.unmount();expect(unlisten).toHaveBeenCalledOnce();
 } finally {info.mockRestore();}
});
