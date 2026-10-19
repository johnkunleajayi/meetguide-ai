import { StrictMode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DesktopAuth } from "../src/components/DesktopAuth";
import * as auth from "../src/lib/auth";

vi.mock("../src/lib/auth", () => ({
  nativeAvailable: vi.fn(), restoreAuth: vi.fn(), login: vi.fn(), logout: vi.fn(), cancelLogin: vi.fn(),
}));
const user = { id: "id", email: "person@example.test", name: "Test Person", avatar_url: "https://example.test/avatar.png" };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(auth.nativeAvailable).mockReturnValue(true);
  vi.mocked(auth.restoreAuth).mockResolvedValue(null);
});
afterEach(cleanup);

it("checks stored native authentication without flashing sign in", async () => {
  render(<StrictMode><DesktopAuth /></StrictMode>);
  expect(screen.getByRole("status").textContent).toContain("Checking");
  expect(screen.queryByText("Sign in with Google")).toBeNull();
  expect(await screen.findByText("Sign in with Google")).toBeTruthy();
});
it("restores the native user and shows avatar, name, and sign out", async () => {
  vi.mocked(auth.restoreAuth).mockResolvedValue(user);
  const { container } = render(<DesktopAuth />);
  expect(await screen.findByText(user.name)).toBeTruthy();
  expect(container.querySelector("img")?.src).toBe(user.avatar_url);
  expect(screen.queryByText("Sign in with Google")).toBeNull();
  fireEvent.error(container.querySelector("img")!);
  expect(container.querySelector("img")).toBeNull();
});
it("uses the native browser flow and only receives user profile data", async () => {
  let complete!: (value: typeof user) => void;
  vi.mocked(auth.login).mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
  render(<DesktopAuth />);
  fireEvent.click(await screen.findByText("Sign in with Google"));
  expect(screen.getByRole("status").textContent).toContain("browser");
  expect(auth.login).toHaveBeenCalledOnce();
  complete(user);
  expect(await screen.findByText(user.name)).toBeTruthy();
});
it("supports cancelling an unfinished browser login", async () => {
  let reject!: (reason: string) => void;
  vi.mocked(auth.login).mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
  vi.mocked(auth.cancelLogin).mockImplementation(async () => { reject("Sign-in cancelled."); });
  render(<DesktopAuth />);
  fireEvent.click(await screen.findByText("Sign in with Google"));
  fireEvent.click(screen.getByText("Cancel sign-in"));
  expect(await screen.findByText("Sign in with Google")).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toBe("Sign-in cancelled.");
});
it("keeps the user visible until native logout succeeds", async () => {
  vi.mocked(auth.restoreAuth).mockResolvedValue(user);
  let complete!: () => void;
  vi.mocked(auth.logout).mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
  render(<DesktopAuth />);
  fireEvent.click(await screen.findByText("Sign out"));
  expect(screen.getByText(user.name)).toBeTruthy();
  expect(screen.getByText("Signing out…").hasAttribute("disabled")).toBe(true);
  complete();
  expect(await screen.findByText("Sign in with Google")).toBeTruthy();
  expect(screen.queryByText(user.name)).toBeNull();
});
it("keeps authentication and offers retry after logout failure", async () => {
  vi.mocked(auth.restoreAuth).mockResolvedValue(user);
  vi.mocked(auth.logout).mockRejectedValueOnce("Unable to revoke your MeetGuide session. Please retry sign out.").mockResolvedValueOnce();
  render(<DesktopAuth />);
  fireEvent.click(await screen.findByText("Sign out"));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByText(user.name)).toBeTruthy();
  fireEvent.click(screen.getByText("Sign out"));
  expect(await screen.findByText("Sign in with Google")).toBeTruthy();
});
it("does not forget a saved session when restore fails", async () => {
  vi.mocked(auth.restoreAuth).mockRejectedValueOnce("offline").mockResolvedValueOnce(user);
  render(<DesktopAuth />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.queryByText("Sign in with Google")).toBeNull();
  fireEvent.click(screen.getByText("Retry"));
  expect(await screen.findByText(user.name)).toBeTruthy();
});
it("explains why a browser-only preview cannot authenticate as a desktop", async () => {
  vi.mocked(auth.nativeAvailable).mockReturnValue(false);
  render(<DesktopAuth />);
  expect(await screen.findByText("Open the Tauri desktop app to sign in securely.")).toBeTruthy();
  expect(auth.restoreAuth).not.toHaveBeenCalled();
});
