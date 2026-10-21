// @vitest-environment node
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { readPrivateDisplay, setPrivateDisplay, subscribePrivateDisplay } from "../src/lib/privateDisplay";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), isTauri: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => () => {}) }));
const source = (path: string) => readFileSync(new URL(`../src-tauri/${path}`, import.meta.url), "utf8");

it("registers native display commands with a local-main-window permission", () => {
  const capability = JSON.parse(source("capabilities/default.json"));
  expect(capability.windows).toEqual(["main"]);
  expect(capability.remote).toBeUndefined();
  expect(capability.permissions).toContain("allow-private-display");
  const allowed = JSON.parse(source("permissions/private-display.toml").match(/commands\.allow\s*=\s*(\[[^\]]*\])/)![1]);
  expect(allowed).toEqual(["private_display_status", "private_display_set"]);
  for (const command of allowed) {
    expect(source("build.rs")).toContain(`"${command}"`);
    expect(source("src/lib.rs")).toContain(`private_display::${command}`);
  }
});

it("uses native status/set commands and the existing event pattern", async () => {
  await readPrivateDisplay();
  expect(invoke).toHaveBeenCalledWith("private_display_status");
  await setPrivateDisplay(true);
  expect(invoke).toHaveBeenCalledWith("private_display_set", { enabled: true });
  await setPrivateDisplay(false);
  expect(invoke).toHaveBeenCalledWith("private_display_set", { enabled: false });
  const callback = vi.fn();
  await subscribePrivateDisplay(callback);
  expect(listen).toHaveBeenCalledWith("meetguide-private-display", expect.any(Function));
});
