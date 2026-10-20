import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ProductDemo, sampleAnswer } from "../src/components/ProductDemo";
import { HeroConversation } from "../src/components/HeroConversation";
import { AppRoutes } from "../src/App";

function media(reduced = false) {
  const listeners = new Set<() => void>();
  const query = { matches: reduced, addEventListener: (_: string, fn: () => void) => listeners.add(fn), removeEventListener: (_: string, fn: () => void) => listeners.delete(fn) };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return { query, change: () => listeners.forEach(fn => fn()), listeners };
}
beforeEach(() => { media(); sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it("plays the fictional conversation through all stages without service requests", async () => {
  vi.useFakeTimers(); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  render(<ProductDemo />);
  const demo = screen.getByRole("region", { name: "Interactive MeetGuide demonstration" });
  const active = () => demo.querySelector('[aria-current="step"]')?.textContent;
  expect(active()).toContain("Listening");
  expect(screen.getByText(/Tell me about a Salesforce integration/)).toBeTruthy();
  expect(screen.getByText(/No microphone, transcription or AI service is connected/)).toBeTruthy();
  for (const [delay, name] of [[1200, "Understanding"], [1000, "Finding relevant experience"], [1000, "Preparing answer"], [1000, "Ready to speak"]] as const) {
    await act(async () => vi.advanceTimersByTime(delay)); expect(active()).toContain(name);
  }
  for (const paragraph of sampleAnswer) expect(screen.getByText(paragraph)).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Pause demo" })).toBeNull();
  await act(async () => vi.advanceTimersByTime(60000)); expect(active()).toContain("Ready to speak");
});

it("supports pause, resume and replay and cleans up timers", async () => {
  vi.useFakeTimers(); render(<ProductDemo />);
  fireEvent.click(screen.getByRole("button", { name: "Pause demo" }));
  await act(async () => vi.advanceTimersByTime(10000));
  expect(document.querySelector('[aria-current="step"]')?.textContent).toContain("Listening");
  fireEvent.click(screen.getByRole("button", { name: "Resume demo" }));
  await act(async () => vi.advanceTimersByTime(1200));
  expect(document.querySelector('[aria-current="step"]')?.textContent).toContain("Understanding");
  fireEvent.click(screen.getByRole("button", { name: "Replay demo" }));
  expect(document.querySelector('[aria-current="step"]')?.textContent).toContain("Listening");
  cleanup(); expect(vi.getTimerCount()).toBe(0);
});

it("shows the complete answer without autoplay in reduced motion with manual steps", async () => {
  media(true); vi.useFakeTimers(); render(<ProductDemo />);
  expect(screen.getByText(sampleAnswer[0])).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Pause demo" })).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "Replay demo" }));
  await act(async () => vi.advanceTimersByTime(60000));
  expect(document.querySelector('[aria-current="step"]')?.textContent).toContain("Listening");
  fireEvent.click(screen.getByRole("button", { name: "Next demo step" }));
  expect(document.querySelector('[aria-current="step"]')?.textContent).toContain("Understanding");
});

it("handles live reduced-motion preference changes and listener cleanup", () => {
  const preference = media(); vi.useFakeTimers(); const view = render(<ProductDemo />);
  act(() => { preference.query.matches = true; preference.change(); });
  expect(screen.getByText(sampleAnswer[0])).toBeTruthy(); expect(vi.getTimerCount()).toBe(0);
  view.unmount(); expect(preference.listeners.size).toBe(0);
});

it("renders the product story, privacy boundaries and accessible mobile navigation", async () => {
  const fetch = vi.fn().mockResolvedValue({ status: 401, ok: false }); vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><AppRoutes /></MemoryRouter>);
  await screen.findByRole("link", { name: "Sign in" });
  for (const heading of ["Interviews", "Sales conversations", "Professional meetings", "Client conversations"]) {
    expect(screen.getByRole("heading", { name: heading, exact: true })).toBeTruthy();
  }
  expect(screen.getByText(/AI providers receive relevant questions, conversation and context/)).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Context Library" })).toBeNull();
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Stay present.Know what to say.");
  expect(screen.getByRole("img").getAttribute("src")).toBe("/images/meetguide-hero-conversation.png");
  expect(screen.getByRole("region", { name: "Interactive MeetGuide demonstration" })).toBeTruthy();
  expect(screen.getByText(/Upload your résumé or CV to your private Context Library/)).toBeTruthy();
  expect(document.getElementById("setup-title")?.textContent).toContain("A workspace to prepare.");
  expect(document.getElementById("closing-title")).toBeTruthy();
  expect(screen.getByText(/not another list of coaching instructions/)).toBeTruthy();
  expect(document.querySelector(".marketing-flow")).toBeNull();
  expect(document.querySelector(".marketing-difference")).toBeNull();
  expect(screen.queryByText("Mention your experience.")).toBeNull();
  expect(screen.queryByText("Prepare on the web. Use MeetGuide Desktop live.")).toBeNull();
  for (const link of document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')) {
    expect(document.getElementById(link.hash.slice(1)), link.hash).toBeTruthy();
  }
  expect(fetch).toHaveBeenCalledTimes(1);
  const menu = screen.getByRole("button", { name: "Open navigation" });
  expect(menu.getAttribute("aria-expanded")).toBe("false"); fireEvent.click(menu);
  expect(screen.getByRole("button", { name: "Close navigation" }).getAttribute("aria-expanded")).toBe("true");
  const navigation = screen.getByRole("navigation", { name: "Main navigation" });
  const link = within(navigation).getByRole("link", { name: "Your context" });
  expect(link.getAttribute("href")).toBe("#your-context"); fireEvent.click(link);
  expect(screen.getByRole("button", { name: "Open navigation" }).getAttribute("aria-expanded")).toBe("false");
});


it("uses the owned complete hero asset without duplicate overlays or service requests", () => {
  vi.useFakeTimers(); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const view = render(<HeroConversation />);
  const image = screen.getByRole("img");
  expect(image.getAttribute("src")).toBe("/images/meetguide-hero-conversation.png");
  expect(image.getAttribute("width")).toBe("1672");
  expect(image.getAttribute("height")).toBe("941");
  expect(image.getAttribute("decoding")).toBe("async");
  expect(image.getAttribute("alt")).toContain("ready-to-speak answer");
  expect(view.container.querySelector(".hero-intelligence")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
  expect(vi.getTimerCount()).toBe(0); expect(fetch).not.toHaveBeenCalled();
});

it("keeps the complete static hero in reduced motion", () => {
  media(true); vi.useFakeTimers(); render(<HeroConversation />);
  expect(screen.getByRole("img")).toBeTruthy();
  expect(vi.getTimerCount()).toBe(0);
});

it("provides an intentional local fallback if the owned asset fails", () => {
  render(<HeroConversation />); fireEvent.error(screen.getByRole("img"));
  expect(screen.queryByRole("img")).toBeNull();
  expect(screen.getByText("Stay in the conversation.")).toBeTruthy();
  expect(screen.getByRole("link").getAttribute("href")).toBe("#demo");
});
