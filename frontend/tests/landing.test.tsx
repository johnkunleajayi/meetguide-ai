import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
const frontendDir = existsSync("src/landing.css") ? process.cwd() : resolve("frontend");
import { LandingMotion, useLandingMotion } from "../src/components/landing/motion";
import { HeroScene, heroAnswer } from "../src/components/landing/HeroScene";
import { CodeAssistDemo, codingQuestions } from "../src/components/landing/CodeAssistDemo";
import { PrivateDisplayDemo } from "../src/components/landing/PrivateDisplayDemo";
import { PreparationJourney } from "../src/components/landing/PreparationJourney";
import { AppRoutes } from "../src/App";
import type { ReactNode } from "react";

function media(reduced = false) {
  const listeners = new Set<() => void>();
  const query = { matches: reduced, addEventListener: (_: string, fn: () => void) => listeners.add(fn), removeEventListener: (_: string, fn: () => void) => listeners.delete(fn) };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return { query, change: () => listeners.forEach(fn => fn()), listeners };
}
function MotionControl() {
  const { paused, toggle } = useLandingMotion();
  return <button onClick={toggle}>{paused ? "Resume" : "Pause"}</button>;
}
function show(children: ReactNode) {
  return render(<MemoryRouter><LandingMotion><MotionControl />{children}</LandingMotion></MemoryRouter>);
}
beforeEach(() => {
  media(); sessionStorage.clear();
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it("plays the hero through listening, detection, preparing, streaming and ready, then loops", () => {
  vi.useFakeTimers(); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const view = show(<HeroScene />);
  const answer = () => view.container.querySelector(".mg-live-answer")!;
  expect(answer().getAttribute("data-show")).toBe("false");
  act(() => vi.advanceTimersByTime(3000));
  expect(view.container.querySelector(".mg-detected")?.getAttribute("data-show")).toBe("true");
  act(() => vi.advanceTimersByTime(1000));
  expect(answer().textContent).toContain("Preparing");
  act(() => vi.advanceTimersByTime(1500));
  expect(answer().textContent).toContain("Responding");
  expect(answer().textContent).not.toContain(heroAnswer);
  act(() => vi.advanceTimersByTime(5000));
  expect(answer().textContent).toContain("Ready to speak");
  expect(answer().textContent).toContain(heroAnswer);
  act(() => vi.advanceTimersByTime(3500));
  expect(answer().getAttribute("data-show")).toBe("false");
  expect(fetch).not.toHaveBeenCalled();
});

it("pauses all demo clocks and cleans up timers", () => {
  vi.useFakeTimers(); const view = show(<><HeroScene /><CodeAssistDemo /></>);
  act(() => vi.advanceTimersByTime(5000));
  fireEvent.click(screen.getByRole("button", { name: "Pause", exact: true }));
  const before = view.container.querySelector(".mg-live-answer")?.textContent;
  act(() => vi.advanceTimersByTime(12000));
  expect(view.container.querySelector(".mg-live-answer")?.textContent).toBe(before);
  expect(vi.getTimerCount()).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "Resume", exact: true }));
  expect(vi.getTimerCount()).toBe(2);
  view.unmount(); expect(vi.getTimerCount()).toBe(0);
});

it("keeps Code Assist in one frame while progressing through contextual follow-ups", () => {
  vi.useFakeTimers(); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const view = show(<CodeAssistDemo />);
  const question = () => view.container.querySelector(".mg-code-question")!.textContent;
  expect(question()).toContain(codingQuestions[0]);
  act(() => vi.advanceTimersByTime(6200)); expect(question()).toContain(codingQuestions[1]);
  act(() => vi.advanceTimersByTime(5000)); expect(question()).toContain(codingQuestions[2]);
  act(() => vi.advanceTimersByTime(5500)); expect(question()).toContain(codingQuestions[3]);
  expect(view.container.querySelector(".mg-language")?.textContent).toBe("JavaScript");
  act(() => vi.advanceTimersByTime(3000));
  expect(view.container.querySelector(".mg-code-output code")?.textContent).toContain("function findDuplicates(values) {\n");
  expect(view.container.querySelectorAll(".mg-code-demo")).toHaveLength(1);
  expect(fetch).not.toHaveBeenCalled();
});

it("lets keyboard users select and read every coding stage without waiting for animation", () => {
  const view = show(<CodeAssistDemo />);
  for (const question of codingQuestions) {
    fireEvent.click(screen.getByRole("button", { name: question, exact: true }));
    expect(view.container.querySelector(".mg-code-question")?.textContent).toContain(question);
    expect(view.container.querySelector(".mg-code-state")?.textContent).toContain("Ready");
  }
  expect(screen.getByText("Read the complete code example").closest("details")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Play sequence" })).toBeTruthy();
});

it("demonstrates Private Display without changing real window protection or making requests", () => {
  vi.useFakeTimers(); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const view = show(<PrivateDisplayDemo />);
  const control = screen.getByRole("switch", { name: "Preview Private Display" });
  expect(control.getAttribute("aria-checked")).toBe("false");
  act(() => vi.advanceTimersByTime(2600));
  expect(control.getAttribute("aria-checked")).toBe("true");
  const screens = view.container.querySelectorAll(".mg-screen-assistant");
  expect(screens[0].getAttribute("data-hidden")).toBe("false");
  expect(screens[1].getAttribute("data-hidden")).toBe("true");
  fireEvent.click(control);
  expect(control.getAttribute("aria-checked")).toBe("false");
  act(() => vi.advanceTimersByTime(10000));
  expect(control.getAttribute("aria-checked")).toBe("false");
  expect(screen.getByText(/universal invisibility is not guaranteed/)).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
});

it("renders complete meaningful demo states and no timers under reduced motion", () => {
  media(true); vi.useFakeTimers();
  const view = show(<><HeroScene /><CodeAssistDemo /><PrivateDisplayDemo /><PreparationJourney /></>);
  expect(view.container.querySelector(".mg-live-answer")?.textContent).toContain(heroAnswer);
  expect(view.container.querySelector(".mg-code-state")?.textContent).toContain("Ready");
  expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
  expect(screen.getAllByRole("tab")).toHaveLength(5);
  expect(vi.getTimerCount()).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: codingQuestions[0], exact: true }));
  expect(view.container.querySelector(".mg-language")?.textContent).toBe("Python");
});

it("reacts to reduced-motion preference changes and releases its media listener", () => {
  const preference = media(); vi.useFakeTimers(); const view = show(<HeroScene />);
  act(() => { preference.query.matches = true; preference.change(); });
  expect(view.container.querySelector(".mg-live-answer")?.textContent).toContain(heroAnswer);
  expect(vi.getTimerCount()).toBe(0);
  view.unmount(); expect(preference.listeners.size).toBe(0);
});

it("does not run offscreen or background-tab demo clocks", () => {
  vi.useFakeTimers();
  const callbacks: IntersectionObserverCallback[] = [];
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) { callbacks.push(callback); }
    observe() {} disconnect() {}
  });
  show(<HeroScene />);
  expect(vi.getTimerCount()).toBe(0);
  act(() => callbacks[0]([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
  expect(vi.getTimerCount()).toBe(1);
  vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  fireEvent(document, new Event("visibilitychange"));
  expect(vi.getTimerCount()).toBe(0);
});

it("renders the full public story, local photography and valid navigation without private content", async () => {
  const fetch = vi.fn().mockResolvedValue({ status: 401, ok: false }); vi.stubGlobal("fetch", fetch);
  const view = render(<MemoryRouter><AppRoutes /></MemoryRouter>);
  await screen.findByRole("link", { name: "Sign in" });
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Bring your best.To every conversation.");
  for (const id of ["product", "how-it-works", "code-assist", "private-display", "use-cases", "privacy", "closing-title"]) expect(document.getElementById(id)).toBeTruthy();
  expect(view.container.textContent).not.toMatch(/Salesforce|\bApex\b|John|Valon/i);
  expect(view.container.textContent).not.toMatch(/Unsplash|Pexels|image credits|photo credit/i);
  expect(view.container.querySelector(".workspace-shell")).toBeNull();
  expect(screen.queryByLabelText("Upload context document")).toBeNull();
  const sources = new Set(Array.from(view.container.querySelectorAll("img"), img => img.getAttribute("src")));
  expect(sources.size).toBe(6);
  for (const source of sources) {
    expect(source?.startsWith("/references/0")).toBe(true);
    expect(existsSync(`${frontendDir}/public${source}`)).toBe(true);
  }
  for (const source of view.container.querySelectorAll("source")) {
    for (const asset of source.srcset.split(",")) expect(existsSync(`${frontendDir}/public${asset.trim().split(" ")[0]}`)).toBe(true);
  }
  for (const link of view.container.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')) expect(document.getElementById(link.hash.slice(1)), link.hash).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(1); // Existing session check only, never demo providers.
  const menu = screen.getByRole("button", { name: "Open navigation" }); fireEvent.click(menu);
  const navigation = screen.getByRole("navigation", { name: "Main navigation" });
  expect(screen.getByRole("button", { name: "Close navigation" }).getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(within(navigation).getByRole("link", { name: "Code Assist" }));
  expect(screen.getByRole("button", { name: "Open navigation" }).getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(menu); fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.getByRole("button", { name: "Open navigation" }).getAttribute("aria-expanded")).toBe("false");
});

it("keeps product storytelling keyboard accessible and meaningful without motion", () => {
  const css = readFileSync(`${frontendDir}/src/landing.css`, "utf8");
  expect(css).toContain("prefers-reduced-motion:reduce");
  expect(css).toContain("max-width:360px");
  const view = show(<PreparationJourney />);
  for (const label of ["Prepare", "Listen", "Understand", "Retrieve", "Respond"]) {
    const tab = screen.getByRole("tab", { name: new RegExp(label) });
    fireEvent.click(tab);
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(tab.id);
  }
  fireEvent.keyDown(screen.getByRole("tab", { name: /Respond/ }), { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: /Prepare/ }).getAttribute("aria-selected")).toBe("true");
  expect(view.container.textContent).toContain("Agree the next project milestone.");
});
