import { BrowserWindow } from "electron";

import { SidecarProcess } from "./process.js";
import type { SidecarStatus, SidecarVersion } from "./types.js";

const HEALTH_INTERVAL_MS = 5_000;

function broadcastStatus(status: SidecarStatus): void {
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send("sidecar:status", status);
  }
}

function isVersion(value: unknown): value is SidecarVersion {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as SidecarVersion).protocol_version === "string" &&
    typeof (value as SidecarVersion).app_version === "string"
  );
}

export class SidecarHealth {
  private timer: NodeJS.Timeout | null = null;

  constructor(private readonly sidecar: SidecarProcess) {
    this.sidecar.on("status", (status) => broadcastStatus(status));
  }

  start(): void {
    this.sidecar.start();
    void this.check();
    this.timer = setInterval(() => void this.check(), HEALTH_INTERVAL_MS);
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    void this.sidecar.stop();
  }

  async reconnect(): Promise<SidecarStatus> {
    await this.sidecar.reconnect();
    await this.check();
    return this.sidecar.snapshot();
  }

  async check(): Promise<void> {
    try {
      const version = await this.sidecar.call("meta.version");
      if (isVersion(version)) {
        this.sidecar.markConnected(version);
      }
    } catch (error) {
      this.sidecar.markDisconnected(error instanceof Error ? error.message : String(error));
    }
  }
}
