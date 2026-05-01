import { globalShortcut } from "electron";
import log from "electron-log";

import type { DesktopSettings, SettingsStore } from "./settings.js";
import type { JsonRpcParams, JsonValue } from "./sidecar/types.js";

export interface ShortcutRegistry {
  register(accelerator: string, callback: () => void): boolean;
  unregister(accelerator: string): void;
}

export interface SidecarCaller {
  call(method: string, params?: JsonRpcParams): Promise<JsonValue>;
}

export class ShortcutController {
  private accelerator: string | null = null;
  private handlingTrigger = false;
  private running = false;

  constructor(
    private readonly settingsStore: SettingsStore,
    private readonly sidecar: SidecarCaller,
    private readonly registry: ShortcutRegistry = globalShortcut
  ) {
    this.settingsStore.on("change", () => this.register());
  }

  register(): void {
    this.unregister();
    const settings = this.settingsStore.get();
    this.accelerator = settings.hotkey;
    const registered = this.registry.register(settings.hotkey, () => {
      log.info("Sabi global shortcut fired", {
        hotkey: settings.hotkey,
        mode: settings.mode,
        pipeline: settings.pipeline,
        running: this.running
      });
      void this.handleTrigger(settings);
    });
    if (registered) {
      log.info("Sabi global shortcut registered", {
        hotkey: settings.hotkey,
        mode: settings.mode,
        pipeline: settings.pipeline
      });
    } else {
      log.warn("Sabi global shortcut registration failed", {
        hotkey: settings.hotkey,
        mode: settings.mode,
        pipeline: settings.pipeline
      });
    }
  }

  unregister(): void {
    if (this.accelerator) {
      this.registry.unregister(this.accelerator);
      this.accelerator = null;
    }
  }

  validateAccelerator(accelerator: string): { ok: boolean; message: string } {
    if (!accelerator.trim()) {
      return { ok: false, message: "Enter a shortcut." };
    }
    if (accelerator === this.accelerator) {
      return { ok: true, message: "Current shortcut is already registered." };
    }
    const registered = this.registry.register(accelerator, () => undefined);
    if (registered) {
      this.registry.unregister(accelerator);
      return { ok: true, message: "Shortcut is available." };
    }
    return { ok: false, message: "Shortcut could not be registered. It may be in use." };
  }

  testAccelerator(
    accelerator: string,
    timeoutMs = 10000
  ): Promise<{ ok: boolean; message: string }> {
    if (!accelerator.trim()) {
      return Promise.resolve({ ok: false, message: "Enter a shortcut." });
    }

    const previous = this.accelerator;
    if (previous) {
      this.registry.unregister(previous);
      this.accelerator = null;
    }

    return new Promise((resolve) => {
      let settled = false;
      let timer: NodeJS.Timeout | null = null;
      const cleanup = () => {
        this.registry.unregister(accelerator);
        if (previous) {
          this.register();
        }
      };
      const finish = (ok: boolean, message: string) => {
        if (settled) {
          return;
        }
        settled = true;
        if (timer) {
          clearTimeout(timer);
        }
        cleanup();
        resolve({ ok, message });
      };
      const registered = this.registry.register(accelerator, () => {
        finish(true, "Shortcut received.");
      });
      if (!registered) {
        finish(false, "Shortcut could not be registered. Choose a different shortcut.");
        return;
      }
      timer = setTimeout(() => {
        finish(false, "Shortcut was not pressed before the test timed out.");
      }, timeoutMs);
    });
  }

  async start(): Promise<void> {
    const settings = this.settingsStore.get();
    try {
      const result = await this.sidecar.call(`dictation.${settings.pipeline}.start`, {
        dry_run: !settings.pasteOnAccept
      });
      this.running = true;
      log.info("Sabi dictation started from global shortcut", {
        pipeline: settings.pipeline,
        result
      });
    } catch (error) {
      log.error("Sabi dictation start failed from global shortcut", error);
      this.running = false;
    }
  }

  async stop(): Promise<void> {
    const settings = this.settingsStore.get();
    try {
      const result = await this.sidecar.call(`dictation.${settings.pipeline}.stop`);
      log.info("Sabi dictation stopped from global shortcut", {
        pipeline: settings.pipeline,
        result
      });
    } catch (error) {
      log.error("Sabi dictation stop failed from global shortcut", error);
    } finally {
      this.running = false;
    }
  }

  private async handleTrigger(settings: DesktopSettings): Promise<void> {
    if (this.handlingTrigger) {
      log.info("Sabi global shortcut ignored while previous trigger is still handling", {
        hotkey: settings.hotkey,
        mode: settings.mode,
        pipeline: settings.pipeline,
        running: this.running
      });
      return;
    }
    if (settings.mode === "toggle" || settings.mode === "push_to_talk") {
      this.handlingTrigger = true;
      try {
        if (this.running) {
          await this.stop();
        } else {
          await this.start();
        }
      } finally {
        this.handlingTrigger = false;
      }
    }
  }
}
