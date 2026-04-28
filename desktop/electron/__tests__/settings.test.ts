import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { SettingsStore } from "../settings.js";

function tempDir(): string {
  return mkdtempSync(join(tmpdir(), "sabi-settings-"));
}

describe("SettingsStore", () => {
  it("writes defaults on first load", () => {
    const store = new SettingsStore(tempDir(), "win32");
    expect(store.get()).toMatchObject({
      mode: "push_to_talk",
      hotkey: "Control+Alt+Space",
      pipeline: "silent",
      onboardingCompleted: false,
      onboardingStep: "welcome"
    });
    expect(JSON.parse(readFileSync(store.filePath, "utf-8"))).toMatchObject(store.get());
  });

  it("round-trips updates", () => {
    const dir = tempDir();
    const store = new SettingsStore(dir, "win32");
    store.update({ mode: "toggle", pipeline: "fused", overlayEnabled: true });
    const reloaded = new SettingsStore(dir, "win32");
    expect(reloaded.get()).toMatchObject({
      mode: "toggle",
      pipeline: "fused",
      overlayEnabled: true
    });
  });

  it("migrates older settings missing onboarding fields", () => {
    const dir = tempDir();
    const store = new SettingsStore(dir, "win32");
    writeFileSync(
      store.filePath,
      JSON.stringify({
        mode: "toggle",
        hotkey: "Control+Alt+Space",
        pipeline: "audio",
        pasteOnAccept: true,
        overlayEnabled: false
      }),
      "utf-8"
    );
    const reloaded = new SettingsStore(dir, "win32");
    expect(reloaded.get()).toMatchObject({
      pipeline: "audio",
      onboardingCompleted: false,
      onboardingStep: "welcome"
    });
  });

  it("persists onboarding resume step", () => {
    const dir = tempDir();
    const store = new SettingsStore(dir, "win32");
    store.update({ onboardingStep: "models" });
    const reloaded = new SettingsStore(dir, "win32");
    expect(reloaded.get().onboardingStep).toBe("models");
  });

  it("quarantines corrupt settings and restores defaults", () => {
    const dir = tempDir();
    const store = new SettingsStore(dir, "win32");
    writeFileSync(store.filePath, "{bad json", "utf-8");
    const reloaded = new SettingsStore(dir, "win32");
    expect(reloaded.get().mode).toBe("push_to_talk");
  });

  it("rejects invalid partial updates", () => {
    const store = new SettingsStore(tempDir(), "win32");
    expect(() => store.update({ pipeline: "bad" } as never)).toThrow();
  });
});
