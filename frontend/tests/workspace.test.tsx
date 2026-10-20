import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../src/App";
import type { AuthUser } from "../src/lib/auth";

const user = { id: "user-qa", email: "jordan@example.test", name: "Jordan Rivera", avatar_url: "https://example.test/avatar.png" };
const document = { id: "cv-1", name: "jordan-cv.txt", context_type: "resume", media_type: "text/plain", size_bytes: 1400, status: "ready", created_at: "2026-10-20T00:00:00Z" };
const reply = (status: number, body: unknown = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
function show(documents = [document], profile: AuthUser | null = user) {
  const fetch = vi.fn((url: string, options?: RequestInit) => Promise.resolve(
    url.endsWith("/me") ? reply(profile ? 200 : 401, profile) :
    url.endsWith("/logout") ? reply(204) : options?.method === "POST" ? reply(201, document) :
    options?.method === "DELETE" ? reply(204) : reply(200, documents)
  ));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter initialEntries={["/app"]}><AppRoutes /></MemoryRouter>);
  return fetch;
}
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); window.document.documentElement.dataset.theme = "light";
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); });

it("welcomes the actual user and reads context once for both readiness and the library", async () => {
  const fetch = show();
  expect(await screen.findByRole("heading", { name: "Welcome back, Jordan." })).toBeTruthy();
  expect(await screen.findByRole("heading", { name: "Your context is ready." })).toBeTruthy();
  expect(screen.getByText("1 context document ready")).toBeTruthy();
  expect(screen.getByText("jordan-cv.txt")).toBeTruthy();
  expect(screen.getByText(user.name)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Preparation" }).getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("link", { name: "Context Library", exact: true }).getAttribute("href")).toBe("#context-library");
  expect(screen.getByRole("link", { name: "Desktop companion" }).getAttribute("href")).toBe("#desktop-companion");
  expect(screen.queryByRole("link", { name: "Public website" })).toBeNull();
  expect(screen.queryByRole("button", { name: /Download/ })).toBeNull();
  expect(fetch.mock.calls.filter(([url]) => url.endsWith("/documents"))).toHaveLength(1);
});

it("guides a new user without inventing a readiness score", async () => {
  show([]);
  expect(await screen.findByRole("heading", { name: "Start with your experience." })).toBeTruthy();
  expect(screen.getByText("No documents yet. Add your résumé to get started.")).toBeTruthy();
  expect(screen.getByLabelText("Upload résumé / CV")).toBeTruthy();
  expect(screen.queryByText(/\d+%/)).toBeNull();
  expect(screen.queryByRole("heading", { name: "Your context is ready." })).toBeNull();
});

it("counts only ready documents and surfaces pending deletions", async () => {
  show([document, { ...document, id: "cv-2", name: "second.pdf" }, { ...document, id: "cv-3", name: "old.docx", status: "deleting" }]);
  expect(await screen.findByText("2 context documents ready")).toBeTruthy();
  expect(screen.getByText("1 document awaiting deletion. Retry in your library.")).toBeTruthy();
  expect(screen.getByText("Deletion pending — retry delete")).toBeTruthy();
});

it("does not mark a library containing only pending deletion as ready", async () => {
  show([{ ...document, status: "deleting" }]);
  expect(await screen.findByRole("heading", { name: "Your library needs attention." })).toBeTruthy();
  expect(screen.getByText("No ready context documents")).toBeTruthy();
});

it("keeps context status unknown after a failed list request and recovers on refresh", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(reply(200, user)).mockResolvedValueOnce(reply(503)).mockResolvedValueOnce(reply(200, [document]));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter initialEntries={["/app"]}><AppRoutes /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Context status unavailable." })).toBeTruthy();
  expect(screen.queryByText("No documents yet. Add your résumé to get started.")).toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: "Refresh documents" })[0]);
  expect(await screen.findByText("1 context document ready")).toBeTruthy();
});

it("shows real upload activity and updates the same readiness state after success", async () => {
  const fetch = show([]);
  await screen.findByText("No documents yet. Add your résumé to get started.");
  let finish!: (value: unknown) => void;
  fetch.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const file = new File(["Fictional professional context"], "jordan-cv.txt", { type: "text/plain" });
  fireEvent.change(screen.getByLabelText("Upload résumé / CV"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload résumé" }));
  expect(screen.getByRole("button", { name: "Uploading…" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByText("Uploading and extracting your document…")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Your context is ready." })).toBeNull();
  await act(async () => finish(reply(201, document)));
  expect(await screen.findByText("1 context document ready")).toBeTruthy();
  expect(fetch).toHaveBeenLastCalledWith("http://127.0.0.1:8000/api/context/documents", expect.objectContaining({ method: "POST", credentials: "include", body: file }));
});

it("accepts an actual file drop and sends it only after submit", async () => {
  const fetch = show([]);
  await screen.findByText("No documents yet. Add your résumé to get started.");
  const file = new File(["Fictional experience"], "jordan-cv.txt", { type: "text/plain" });
  const dropzone = screen.getByText("Drag a résumé into this area, or choose a file.").parentElement!;
  fireEvent.dragEnter(dropzone, { dataTransfer: { types: ["Files"] } });
  expect(screen.getByText("Drop your résumé here")).toBeTruthy();
  fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
  expect(screen.getByText("jordan-cv.txt")).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Upload résumé" }));
  expect(await screen.findByText("1 context document ready")).toBeTruthy();
});

it("preserves delete cancellation and removes the last ready document after success", async () => {
  const fetch = show();
  const confirm = vi.fn(() => false); vi.stubGlobal("confirm", confirm);
  fireEvent.click(await screen.findByRole("button", { name: "Delete jordan-cv.txt" }));
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(screen.getByText("1 context document ready")).toBeTruthy();
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Delete jordan-cv.txt" }));
  expect(await screen.findByRole("heading", { name: "Start with your experience." })).toBeTruthy();
  expect(within(screen.getByRole("list", { name: "Your context documents" })).queryByText("jordan-cv.txt")).toBeNull();
  expect(confirm).toHaveBeenLastCalledWith("Delete jordan-cv.txt and its extracted context?");
});

it("retains the document on delete failure and allows retry", async () => {
  const fetch = show(); vi.stubGlobal("confirm", vi.fn(() => true));
  await screen.findByText("1 context document ready");
  fetch.mockResolvedValueOnce(reply(503));
  fireEvent.click(screen.getByRole("button", { name: "Delete jordan-cv.txt" }));
  expect((await screen.findByRole("alert")).textContent).toContain("unavailable");
  expect(screen.getByText("jordan-cv.txt")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Delete jordan-cv.txt" }));
  expect(await screen.findByText("No documents yet. Add your résumé to get started.")).toBeTruthy();
});

it("keeps anonymous visitors behind the existing Google gate without document requests", async () => {
  const fetch = show([], null);
  expect(await screen.findByRole("link", { name: "Sign in with Google" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Context Library" })).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("preserves theme switching and returns to the public site on successful logout", async () => {
  const fetch = show(); await screen.findByText("1 context document ready");
  fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
  expect(window.document.documentElement.dataset.theme).toBe("dark");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByRole("link", { name: "Sign in" });
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Context Library" })).toBeNull());
  expect(fetch).toHaveBeenLastCalledWith("http://127.0.0.1:8000/api/auth/logout", { method: "POST", credentials: "include" });
});

it("uses a timeless fallback rather than a hard-coded name when the profile has no name", async () => {
  show([], { ...user, name: null });
  expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeTruthy();
});


it("rejects multi-file drops without accidentally submitting a previous selection", async () => {
  const fetch = show([]);
  await screen.findByText("No documents yet. Add your résumé to get started.");
  const file = new File(["Fictional context"], "previous.txt");
  fireEvent.change(screen.getByLabelText("Upload résumé / CV"), { target: { files: [file] } });
  const dropzone = screen.getByText("Drag a résumé into this area, or choose a file.").parentElement!;
  fireEvent.drop(dropzone, { dataTransfer: { files: [file, new File(["x"], "another.txt")] } });
  expect((await screen.findByRole("alert")).textContent).toContain("one résumé");
  expect(screen.queryByText("previous.txt")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Upload résumé" }));
  expect(fetch).toHaveBeenCalledTimes(2);
});
