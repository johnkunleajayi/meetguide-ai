import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { AppRoutes } from "../src/App";
import { GOOGLE_LOGIN_URL, rememberWorkspace } from "../src/lib/auth";

const user = { id: "test-user", email: "test@example.test", name: "Test Person", avatar_url: "https://example.test/avatar.png" };
const document = { id: "doc-1", name: "fictional-cv.txt", context_type: "resume", media_type: "text/plain", size_bytes: 20, status: "ready", created_at: "2026-10-19T00:00:00Z" };
const reply = (status: number, body: unknown = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
function Location() { return <output data-testid="location">{useLocation().pathname}</output>; }
function show(route = "/", authenticated = true) {
  const fetch = vi.fn((url: string) => Promise.resolve(
    url.endsWith("/me") ? reply(authenticated ? 200 : 401, authenticated ? user : null) :
    url.endsWith("/logout") ? reply(204) : url.endsWith("/preparations") ? reply(200, []) : reply(200, [document])
  ));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter initialEntries={[route]}><AppRoutes /><Location /></MemoryRouter>);
  return fetch;
}
beforeEach(() => {
  sessionStorage.clear(); localStorage.clear(); documentRootTheme("light");
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
function documentRootTheme(theme: string) { window.document.documentElement.dataset.theme = theme; }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); localStorage.clear(); });

it("keeps / public when signed out, with marketing and no Context Library requests", async () => {
  const fetch = show("/", false);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Be present");
  expect((await screen.findByRole("link", { name: "Sign in" })).getAttribute("href")).toBe(GOOGLE_LOGIN_URL);
  expect(within(screen.getByRole("banner")).getByRole("link", { name: "Get MeetGuide", exact: true }).getAttribute("href")).toBe(GOOGLE_LOGIN_URL);
  expect(screen.queryByRole("heading", { name: "What are you preparing for?" })).toBeNull();
  expect(screen.queryByLabelText("Upload context document")).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("keeps signed-in users on the public page and links to the real workspace", async () => {
  const fetch = show();
  fireEvent.click(await screen.findByRole("link", { name: "Open Workspace" }));
  expect(await screen.findByText("fictional-cv.txt")).toBeTruthy();
  expect(screen.getByTestId("location").textContent).toBe("/app");
  expect(screen.getByText(user.name)).toBeTruthy();
  expect(screen.queryByText("Know what to say.")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: "MeetGuide AI home" }));
  expect(await screen.findByRole("link", { name: "Open Workspace" })).toBeTruthy();
  expect(screen.getByTestId("location").textContent).toBe("/");
  expect(screen.queryByRole("heading", { name: "What are you preparing for?" })).toBeNull();
  expect(fetch.mock.calls.filter(([url]) => url.endsWith("/me"))).toHaveLength(1);
});

it("direct authenticated /app renders identity and Context Library without marketing", async () => {
  show("/app");
  expect(await screen.findByRole("heading", { name: "What are you preparing for?" })).toBeTruthy();
  expect(await screen.findByText("fictional-cv.txt")).toBeTruthy();
  expect(screen.getByLabelText("Upload context document")).toBeTruthy();
  expect(screen.getByText(user.name)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
  expect(screen.getByText(/Use MeetGuide Desktop for live transcription/)).toBeTruthy();
  expect(screen.queryByRole("navigation", { name: "Main navigation" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Public website" })).toBeNull();
});

it("gates unauthenticated /app without fetching documents and offers existing Google flow", async () => {
  const fetch = show("/app", false);
  expect(screen.queryByLabelText("Upload context document")).toBeNull();
  const login = await screen.findByRole("link", { name: "Sign in with Google" });
  expect(login.getAttribute("href")).toBe(GOOGLE_LOGIN_URL);
  login.addEventListener("click", (event) => event.preventDefault(), { once: true });
  fireEvent.click(login);
  expect(sessionStorage.getItem("meetguide-open-workspace")).toBe("true");
  expect(fetch).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("link", { name: "Back to public website" }));
  expect(screen.getByTestId("location").textContent).toBe("/");
});

it("returns an authenticated OAuth callback at / to /app using only fixed route intent", async () => {
  rememberWorkspace();
  expect(sessionStorage.getItem("meetguide-open-workspace")).toBe("true");
  // Wait for callback navigation before querying the destination's document request.
  show();
  await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/app"), { timeout: 5000 });
  expect(await screen.findByText("fictional-cv.txt")).toBeTruthy();
  expect(screen.getByTestId("location").textContent).toBe("/app");
  expect(sessionStorage.getItem("meetguide-open-workspace")).toBeNull();
});

it("public Sign in and Get started record workspace intent without changing OAuth URLs", async () => {
  show("/", false);
  for (const name of ["Sign in", "Get MeetGuide"]) {
    const link = await within(screen.getByRole("banner")).findByRole("link", { name });
    link.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    expect(sessionStorage.getItem("meetguide-open-workspace")).toBe("true");
    sessionStorage.clear();
  }
});

it("successful logout clears private content and returns to / with cookie-based POST", async () => {
  const fetch = show("/app");
  await screen.findByText("fictional-cv.txt");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByRole("link", { name: "Sign in" });
  await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
  expect(screen.queryByText("fictional-cv.txt")).toBeNull();
  expect(screen.queryByText(user.name)).toBeNull();
  expect(fetch).toHaveBeenLastCalledWith("http://127.0.0.1:8000/api/auth/logout", { method: "POST", credentials: "include" });
});

it("failed logout retains the workspace and allows retry", async () => {
  const fetch = show("/app");
  await screen.findByText("fictional-cv.txt");
  fetch.mockResolvedValueOnce(reply(503));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Unable to sign out");
  expect(screen.getByTestId("location").textContent).toBe("/app");
  expect(screen.getByText("fictional-cv.txt")).toBeTruthy();
});

it("never mounts private content during loading or an auth-check failure", async () => {
  const fetch = vi.fn().mockImplementationOnce(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetch);
  const view = render(<MemoryRouter initialEntries={["/app"]}><AppRoutes /></MemoryRouter>);
  expect(screen.getByText("Checking your sign-in…")).toBeTruthy();
  expect(screen.queryByLabelText("Upload context document")).toBeNull();
  view.unmount();
  fetch.mockRejectedValueOnce(new Error("offline"));
  render(<MemoryRouter initialEntries={["/app"]}><AppRoutes /></MemoryRouter>);
  await screen.findByRole("button", { name: "Retry sign-in check" });
  expect(screen.queryByLabelText("Upload context document")).toBeNull();
});

it("preserves theme switching when navigating between the public site and workspace", async () => {
  show();
  fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
  expect(window.document.documentElement.dataset.theme).toBe("dark");
  fireEvent.click(await screen.findByRole("link", { name: "Open Workspace" }));
  await screen.findByText("fictional-cv.txt");
  expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
  fireEvent.click(screen.getByRole("link", { name: "MeetGuide AI home" }));
  await waitFor(() => expect(window.document.documentElement.dataset.theme).toBe("light"));
});
