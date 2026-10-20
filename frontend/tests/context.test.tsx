import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ContextLibrary } from "../src/components/ContextLibrary";
import App from "../src/App";
import { deleteDocument, listDocuments, MAX_DOCUMENT_BYTES, uploadDocument } from "../src/lib/context";

const document = { id: "doc-1", name: "resume.txt", context_type: "resume", media_type: "text/plain", size_bytes: 20, status: "ready", created_at: "2026-10-19T00:00:00Z" };
const reply = (status: number, body: unknown = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
function fetchMock() { const mock = vi.fn(); vi.stubGlobal("fetch", mock); return mock; }
afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState({}, "", "/"); sessionStorage.clear(); });

it("lists private documents and uploads a résumé with credentials", async () => {
  const fetch = fetchMock().mockResolvedValueOnce(reply(200, [])).mockResolvedValueOnce(reply(201, document));
  render(<ContextLibrary />);
  expect(screen.getByRole("status").textContent).toContain("Loading");
  await screen.findByText("No documents yet. Add your résumé to get started.");
  const file = new File(["Leadership experience"], "resume.txt", { type: "text/plain" });
  fireEvent.change(screen.getByLabelText("Upload résumé / CV"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload résumé" }));
  expect(await screen.findByText("resume.txt")).toBeTruthy();
  expect(fetch).toHaveBeenLastCalledWith("http://127.0.0.1:8000/api/context/documents", expect.objectContaining({ method: "POST", credentials: "include", body: file, headers: { "Content-Type": "application/octet-stream", "X-Document-Name": "resume.txt" } }));
});
it("deletes a document after confirmation and removes it from the list", async () => {
  const fetch = fetchMock().mockResolvedValueOnce(reply(200, [document])).mockResolvedValueOnce(reply(204));
  vi.stubGlobal("confirm", vi.fn(() => true));
  render(<ContextLibrary />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete resume.txt" }));
  await waitFor(() => expect(screen.queryByText("resume.txt")).toBeNull());
  expect(fetch).toHaveBeenLastCalledWith("http://127.0.0.1:8000/api/context/documents/doc-1", expect.objectContaining({ method: "DELETE", credentials: "include" }));
});
it("shows upload errors without inventing a ready document", async () => {
  fetchMock().mockResolvedValueOnce(reply(200, [])).mockResolvedValueOnce(reply(422, { detail: "No readable text found." }));
  render(<ContextLibrary />); await screen.findByText("No documents yet. Add your résumé to get started.");
  fireEvent.change(screen.getByLabelText("Upload résumé / CV"), { target: { files: [new File(["bad pdf"], "cv.pdf")] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload résumé" }));
  expect((await screen.findByRole("alert")).textContent).toContain("No readable text");
  expect(within(screen.getByRole("list", { name: "Your context documents" })).queryByText("cv.pdf")).toBeNull();
});
it("validates size, empty and unsupported files before sending", async () => {
  const fetch = fetchMock();
  await expect(uploadDocument(new File([], "empty.txt"), new AbortController().signal)).rejects.toThrow("empty");
  await expect(uploadDocument(new File(["bad"], "bad.exe"), new AbortController().signal)).rejects.toThrow("PDF");
  const oversized = new File(["a"], "large.txt"); Object.defineProperty(oversized, "size", { value: MAX_DOCUMENT_BYTES + 1 });
  await expect(uploadDocument(oversized, new AbortController().signal)).rejects.toThrow("5 MB");
  expect(fetch).not.toHaveBeenCalled();
});
it("handles session expiration and server failures", async () => {
  fetchMock().mockResolvedValueOnce(reply(401)).mockResolvedValueOnce(reply(503));
  await expect(listDocuments(new AbortController().signal)).rejects.toThrow("expired");
  await expect(deleteDocument("doc-1", new AbortController().signal)).rejects.toThrow("retry");
});
it("aborts in-flight document requests when unmounted", () => {
  const fetch = fetchMock().mockImplementation(() => new Promise(() => {}));
  const { unmount } = render(<ContextLibrary />); unmount();
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
});
it("only mounts the library in the authenticated workspace and clears it on logout", async () => {
  window.history.replaceState({}, "", "/app");
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const fetch = fetchMock().mockResolvedValueOnce(reply(200, { id: "user-1", email: "jane@example.test", name: "Jane", avatar_url: null }))
    .mockResolvedValueOnce(reply(200, [document])).mockResolvedValueOnce(reply(204));
  render(<App />);
  expect(await screen.findByText("resume.txt")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await screen.findByText("Sign in");
  expect(screen.queryByText("resume.txt")).toBeNull();
  expect(screen.queryByRole("heading", { name: "Context Library" })).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(3);
});
it("keeps the library hidden while signed out", async () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const fetch = fetchMock().mockResolvedValue(reply(401)); render(<App />);
  await screen.findByText("Sign in");
  expect(screen.queryByRole("heading", { name: "Context Library" })).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});

