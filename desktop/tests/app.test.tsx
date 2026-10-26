import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../src/App";
import * as auth from "../src/lib/auth";
vi.mock("../src/lib/auth", () => ({ nativeAvailable: vi.fn(() => true), restoreAuth: vi.fn(), login: vi.fn(), logout: vi.fn(), cancelLogin: vi.fn() }));
vi.mock("../src/components/AudioSession", () => ({ AudioSession: ({ authenticated, onBusyChange }: { authenticated: boolean; onBusyChange: (value: boolean) => void }) => <section aria-label="Session controls" data-authenticated={authenticated}><button onClick={() => onBusyChange(true)}>Starting session</button><button onClick={() => onBusyChange(false)}>Session started</button></section> }));
const profile = { id: "test-person", name: "Morgan Lee", email: "morgan@example.test", avatar_url: null };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(auth.nativeAvailable).mockReturnValue(true);
  vi.mocked(auth.restoreAuth).mockResolvedValue(null);
  vi.mocked(auth.login).mockResolvedValue(profile);
  vi.mocked(auth.logout).mockResolvedValue();
  localStorage.clear(); delete document.documentElement.dataset.theme;
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("keeps account actions, the skip link and the same mounted session shell across sign-in/out", async () => {
  render(<App />);
  expect(screen.getByRole("link", { name: "Skip to conversation workspace" }).getAttribute("href")).toBe("#main");
  expect(screen.getByRole("main").id).toBe("main");
  const session = screen.getByRole("region", { name: "Session controls" });
  fireEvent.click(await screen.findByRole("button", { name: "Sign in with Google" }));
  await screen.findByText(profile.name);
  await waitFor(() => expect(session.dataset.authenticated).toBe("true"));
  expect(screen.queryByText("Your conversation,")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByRole("button", { name: "Sign in with Google" });
  expect(session).toBe(screen.getByRole("region", { name: "Session controls" }));
  expect(auth.logout).toHaveBeenCalledOnce();
});
it("preserves the existing local theme preference and accessible toggle labels", async () => {
  render(<App />); await screen.findByRole("button", { name: "Sign in with Google" });
  fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("meetguide-desktop-theme")).toBe("dark");
  fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
  expect(document.documentElement.dataset.theme).toBe("light");
});
it("keeps logout disabled while the existing session transition is busy", async () => {
  vi.mocked(auth.restoreAuth).mockResolvedValue(profile);
  render(<App />); await screen.findByText(profile.name);
  fireEvent.click(screen.getByRole("button", { name: "Starting session" }));
  expect((screen.getByRole("button", { name: "Sign out" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Session started" }));
  expect((screen.getByRole("button", { name: "Sign out" }) as HTMLButtonElement).disabled).toBe(false);
  expect(auth.logout).not.toHaveBeenCalled();
});
