import { globalShortcut } from "electron";

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
    this.registry.register(settings.hotkey, () => {
      void this.handleTrigger(settings);
    });
  }

  unregister(): void {
    if (this.accelerator) {
      this.registry.unregister(this.accelerator);
      this.accelerator = null;
    }
  }

  async start(): Promise<void> {
    const settings = this.settingsStore.get();
    await this.sidecar.call(`dictation.${settings.pipeline}.start`, {
      dry_run: !settings.pasteOnAccept
    });
    this.running = true;
  }

  async stop(): Promise<void> {
    const settings = this.settingsStore.get();
    await this.sidecar.call(`dictation.${settings.pipeline}.stop`);
    this.running = false;
  }

  private async handleTrigger(settings: DesktopSettings): Promise<void> {
    if (settings.mode === "toggle" || settings.mode === "push_to_talk") {
      if (this.running) {
        await this.stop();
      } else {
        await this.start();
      }
    }
  }
}
