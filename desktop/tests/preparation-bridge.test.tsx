// @vitest-environment node
import { readFileSync } from "node:fs";
import { expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { activatePreparation, readPreparations } from "../src/lib/preparation";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => []) }));
const source = (path: string) => readFileSync(new URL(`../src-tauri/${path}`, import.meta.url), "utf8");

it("declares both preparation bridge commands in the Tauri build manifest and handler", () => {
  for (const command of ["preparation_list", "preparation_activate"]) {
    expect(source("build.rs")).toContain(`"${command}"`);
    expect(source("src/lib.rs")).toContain(`preparation::${command}`);
  }
});

it("grants only preparation commands to the local main-window capability", () => {
  const capability = JSON.parse(source("capabilities/default.json"));
  expect(capability.windows).toEqual(["main"]);
  expect(capability.remote).toBeUndefined();
  expect(capability.permissions).toContain("allow-session-preparation");
  const permission = source("permissions/preparation.toml");
  expect(permission).toContain('identifier = "allow-session-preparation"');
  const allowed = JSON.parse(permission.match(/commands\.allow\s*=\s*(\[[^\]]*\])/)![1]);
  expect(allowed.sort()).toEqual(["preparation_activate", "preparation_list"]);
});

it("uses the permitted native commands without exposing authentication to JavaScript", async () => {
  await readPreparations();
  expect(invoke).toHaveBeenCalledWith("preparation_list");
  await activatePreparation("fictional-preparation-id");
  expect(invoke).toHaveBeenCalledWith("preparation_activate", { id: "fictional-preparation-id" });
});
