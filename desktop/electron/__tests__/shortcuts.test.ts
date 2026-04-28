import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { ShortcutController, type ShortcutRegistry } from "../shortcuts.js";
import { SettingsStore } from "../settings.js";

function makeHarness() {
  let callback: (() => void) | null = null;
  const registry: ShortcutRegistry = {
    register: vi.fn((_accelerator, cb) => {
      callback = cb;
      return true;
    }),
    unregister: vi.fn()
  };
  const sidecar = { call: vi.fn(async () => null) };
  const store = new SettingsStore(mkdtempSync(join(tmpdir(), "sabi-shortcuts-")), "win32");
  const shortcuts = new ShortcutController(store, sidecar, registry);
  return { callback: () => callback?.(), registry, shortcuts, sidecar, store };
}

describe("ShortcutController", () => {
  it("registers the accelerator from settings", () => {
    const { registry, shortcuts } = makeHarness();
    shortcuts.register();
    expect(registry.register).toHaveBeenCalledWith("Control+Alt+Space", expect.any(Function));
  });

  it("toggles start and stop for toggle mode", async () => {
    const { callback, shortcuts, sidecar, store } = makeHarness();
    store.update({ mode: "toggle", pipeline: "fused" });
    shortcuts.register();
    callback();
    await vi.waitFor(() => expect(sidecar.call).toHaveBeenCalledWith("dictation.fused.start", { dry_run: false }));
    callback();
    await vi.waitFor(() => expect(sidecar.call).toHaveBeenCalledWith("dictation.fused.stop"));
  });

  it("uses repeated presses for push-to-talk under Electron globalShortcut", async () => {
    const { callback, shortcuts, sidecar } = makeHarness();
    shortcuts.register();
    callback();
    await vi.waitFor(() => expect(sidecar.call).toHaveBeenCalledWith("dictation.silent.start", { dry_run: false }));
    callback();
    await vi.waitFor(() => expect(sidecar.call).toHaveBeenCalledWith("dictation.silent.stop"));
  });

  it("unregisters and re-registers when settings change", () => {
    const { registry, shortcuts, store } = makeHarness();
    shortcuts.register();
    store.update({ hotkey: "Control+Shift+Space" });
    expect(registry.unregister).toHaveBeenCalledWith("Control+Alt+Space");
    expect(registry.register).toHaveBeenLastCalledWith("Control+Shift+Space", expect.any(Function));
  });
});
