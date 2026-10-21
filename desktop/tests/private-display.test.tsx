import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PrivateDisplay } from "../src/components/PrivateDisplay";
import * as bridge from "../src/lib/privateDisplay";

vi.mock("../src/lib/privateDisplay", () => ({
  privateDisplayAvailable: vi.fn(), readPrivateDisplay: vi.fn(),
  setPrivateDisplay: vi.fn(), subscribePrivateDisplay: vi.fn(),
}));
const status = (state: bridge.PrivateDisplayStatus["state"], revision = 1): bridge.PrivateDisplayStatus => ({
  state, revision, requestedEnabled: state !== "off", message: null,
});
let update: (value: bridge.PrivateDisplayStatus) => void;
const unlisten = vi.fn();
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(bridge.privateDisplayAvailable).mockReturnValue(true);
  vi.mocked(bridge.readPrivateDisplay).mockResolvedValue(status("on"));
  vi.mocked(bridge.setPrivateDisplay).mockResolvedValue(status("off", 2));
  vi.mocked(bridge.subscribePrivateDisplay).mockImplementation(async callback => {
    update = callback;
    return unlisten;
  });
});
afterEach(cleanup);

it("does not claim ON until native read-back arrives", async () => {
  let finish!: (value: bridge.PrivateDisplayStatus) => void;
  vi.mocked(bridge.readPrivateDisplay).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<PrivateDisplay />);
  expect(screen.getByText("Private Display: Checking…")).toBeTruthy();
  expect(screen.queryByText("Private Display: ON")).toBeNull();
  await waitFor(() => expect(bridge.readPrivateDisplay).toHaveBeenCalledOnce());
  await act(async () => finish(status("on")));
  expect(screen.getByText("Private Display: ON")).toBeTruthy();
  expect(bridge.setPrivateDisplay).not.toHaveBeenCalled();
});

it("turns OFF only after native confirmation and can turn back ON", async () => {
  let finish!: (value: bridge.PrivateDisplayStatus) => void;
  vi.mocked(bridge.setPrivateDisplay).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<PrivateDisplay />);
  fireEvent.click(await screen.findByRole("button", { name: "Turn off Private Display" }));
  expect(bridge.setPrivateDisplay).toHaveBeenCalledWith(false);
  expect(screen.getByText("Private Display: ON")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Check status" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => finish(status("off", 2)));
  expect(screen.getByText("Private Display: OFF")).toBeTruthy();
  vi.mocked(bridge.setPrivateDisplay).mockResolvedValueOnce(status("on", 3));
  fireEvent.click(screen.getByRole("button", { name: "Turn on Private Display" }));
  await screen.findByText("Private Display: ON");
  expect(bridge.setPrivateDisplay).toHaveBeenLastCalledWith(true);
});

it("shows actual OFF and the Windows failure message after a rejected ON request", async () => {
  vi.mocked(bridge.readPrivateDisplay).mockResolvedValue(status("off"));
  vi.mocked(bridge.setPrivateDisplay).mockResolvedValue({ ...status("off", 2), requestedEnabled: true, message: "Windows could not change Private Display." });
  render(<PrivateDisplay />);
  fireEvent.click(await screen.findByRole("button", { name: "Turn on Private Display" }));
  await screen.findByText("Windows could not change Private Display.");
  expect(screen.getByText("Private Display: OFF")).toBeTruthy();
  expect(screen.queryByText("Private Display: ON")).toBeNull();
});

it("marks a failed command as unverified without displaying raw errors", async () => {
  vi.mocked(bridge.setPrivateDisplay).mockRejectedValue("raw native diagnostic");
  render(<PrivateDisplay />);
  fireEvent.click(await screen.findByRole("button", { name: "Turn off Private Display" }));
  await screen.findByText("Private Display: Unverified");
  expect(screen.queryByText("raw native diagnostic")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Check status" }));
  await screen.findByText("Private Display: ON");
});

it("keeps newer native lifecycle events when an older status response arrives", async () => {
  let finish!: (value: bridge.PrivateDisplayStatus) => void;
  vi.mocked(bridge.readPrivateDisplay).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<PrivateDisplay />);
  await waitFor(() => expect(bridge.readPrivateDisplay).toHaveBeenCalledOnce());
  act(() => update(status("on", 3)));
  await act(async () => finish(status("off", 1)));
  expect(screen.getByText("Private Display: ON")).toBeTruthy();
  act(() => update(status("off", 4)));
  expect(screen.getByText("Private Display: OFF")).toBeTruthy();
});

it("reports limited protection honestly and offers normal capture restoration", async () => {
  vi.mocked(bridge.readPrivateDisplay).mockResolvedValue({ ...status("limited"), message: "Windows has not confirmed capture exclusion." });
  render(<PrivateDisplay />);
  await screen.findByText("Private Display: Limited");
  expect(screen.queryByText("Private Display: ON")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Turn off Private Display" }));
  await screen.findByText("Private Display: OFF");
});

it("disables the control outside Tauri and does not invoke native commands", async () => {
  vi.mocked(bridge.privateDisplayAvailable).mockReturnValue(false);
  render(<PrivateDisplay />);
  await screen.findByText("Private Display: Unavailable");
  expect((screen.getByRole("button", { name: "Turn on Private Display" }) as HTMLButtonElement).disabled).toBe(true);
  expect(bridge.readPrivateDisplay).not.toHaveBeenCalled();
  expect(bridge.subscribePrivateDisplay).not.toHaveBeenCalled();
});

it("reports unsupported native platforms without claiming protection", async () => {
  vi.mocked(bridge.readPrivateDisplay).mockResolvedValue(status("unsupported"));
  render(<PrivateDisplay />);
  await screen.findByText("Private Display: Unavailable");
  expect(screen.queryByText("Private Display: ON")).toBeNull();
});

it("cleans up listeners without disabling native protection on React unmount", async () => {
  const view = render(<PrivateDisplay />);
  await screen.findByText("Private Display: ON");
  view.unmount();
  expect(unlisten).toHaveBeenCalledOnce();
  expect(bridge.setPrivateDisplay).not.toHaveBeenCalled();
});
