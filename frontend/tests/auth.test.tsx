import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AuthControls } from "../src/components/AuthControls";
import { getCurrentUser, GOOGLE_LOGIN_URL } from "../src/lib/auth";

const user = { id: "user-1", email: "jane@example.com", name: "Jane Doe", avatar_url: "https://example.com/avatar.png" };
const reply = (status: number, body: unknown = null) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const mockFetch = () => {
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);
  return mock;
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("web session authentication", () => {
  it("includes credentials on startup and treats 401 as signed out", async () => {
    const fetch = mockFetch().mockResolvedValue(reply(401));
    render(<AuthControls />);
    expect(screen.getByRole("status").textContent).toContain("Checking");
    expect(screen.queryByText("Sign in")).toBeNull();
    expect((await screen.findByText("Sign in")).getAttribute("href")).toBe(GOOGLE_LOGIN_URL);
    expect(screen.getByText("Get started").getAttribute("href")).toBe(GOOGLE_LOGIN_URL);
    expect(fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/api/auth/me", expect.objectContaining({ credentials: "include", cache: "no-store", signal: expect.any(AbortSignal) }));
  });
  it("shows the current user and avatar instead of sign-in controls", async () => {
    mockFetch().mockResolvedValue(reply(200, user));
    const { container } = render(<AuthControls />);
    await screen.findByText("Jane Doe");
    expect(container.querySelector("img")?.getAttribute("src")).toBe(user.avatar_url);
    expect(screen.queryByText("Sign in")).toBeNull();
    expect(screen.queryByText("Get started")).toBeNull();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("J")).toBeTruthy();
  });
  it("falls back to email and initials when Google has no profile details", async () => {
    mockFetch().mockResolvedValue(reply(200, { ...user, name: null, avatar_url: null }));
    render(<AuthControls />);
    expect(await screen.findByText(user.email)).toBeTruthy();
    expect(screen.getByText("J")).toBeTruthy();
  });
  it("posts logout with cookies and returns to signed-out controls after success", async () => {
    const fetch = mockFetch().mockResolvedValueOnce(reply(200, user));
    let finish!: (value: unknown) => void;
    fetch.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    render(<AuthControls />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(screen.getByRole("button", { name: "Signing out…" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(user.name)).toBeTruthy();
    expect(fetch).toHaveBeenLastCalledWith("http://127.0.0.1:8000/api/auth/logout", { method: "POST", credentials: "include" });
    finish(reply(204));
    expect(await screen.findByText("Sign in")).toBeTruthy();
    expect(screen.queryByText(user.name)).toBeNull();
  });
  it("preserves the authenticated state on logout failure and allows retry", async () => {
    mockFetch().mockResolvedValueOnce(reply(200, user)).mockResolvedValueOnce(reply(503)).mockResolvedValueOnce(reply(204));
    render(<AuthControls />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to sign out");
    expect(screen.getByText(user.name)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("Sign in")).toBeTruthy();
  });
  it("reports network failure and retries the startup check", async () => {
    mockFetch().mockRejectedValueOnce(new TypeError("network")).mockResolvedValueOnce(reply(401));
    render(<AuthControls />);
    await screen.findByRole("alert");
    expect(screen.queryByText("Sign in")).toBeNull();
    fireEvent.click(screen.getByText("Retry"));
    expect(await screen.findByText("Sign in")).toBeTruthy();
  });
  it("does not mistake server errors or invalid responses for unauthenticated", async () => {
    mockFetch().mockResolvedValueOnce(reply(503)).mockResolvedValueOnce(reply(200, {}));
    await expect(getCurrentUser(new AbortController().signal)).rejects.toThrow("Unable to check");
    await expect(getCurrentUser(new AbortController().signal)).rejects.toThrow("Unable to check");
  });
  it("aborts discarded startup checks in StrictMode and on unmount", async () => {
    const fetch = mockFetch().mockResolvedValue(reply(401));
    const { unmount } = render(<StrictMode><AuthControls /></StrictMode>);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    unmount();
    expect(fetch.mock.calls[1][1].signal.aborted).toBe(true);
  });
});
