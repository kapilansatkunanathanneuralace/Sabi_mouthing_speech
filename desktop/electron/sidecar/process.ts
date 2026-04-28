import { EventEmitter } from "node:events";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

import log from "electron-log";

import { JsonRpcClient } from "./rpc.js";
import { resolveSidecarCommand } from "./path.js";
import type { JsonRpcParams, JsonValue, SidecarStatus, SidecarVersion } from "./types.js";

const MAX_RESTARTS = 3;
const RESTART_DELAY_MS = 1_000;

export class SidecarProcess extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private rpc: JsonRpcClient | null = null;
  private stoppedByUser = false;
  private restartTimer: NodeJS.Timeout | null = null;
  private status: SidecarStatus = { state: "stopped", restarts: 0 };

  start(): void {
    if (this.child) {
      return;
    }
    this.stoppedByUser = false;
    this.setStatus({ ...this.status, state: "starting", error: undefined });
    const command = resolveSidecarCommand();
    log.info("Starting Sabi sidecar", command);
    const child = spawn(command.command, command.args, {
      cwd: command.cwd,
      env: { ...process.env, SABI_SIDECAR_NO_HOTKEY: "1" },
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true
    });
    this.child = child;
    this.rpc = new JsonRpcClient(child.stdout, child.stdin);
    this.rpc.on("notification", (payload) => this.emit("notification", payload));
    child.stderr.on("data", (chunk: Buffer | string) => {
      log.info(`[sidecar] ${chunk.toString().trimEnd()}`);
    });
    child.on("error", (error) => {
      this.setStatus({ ...this.status, state: "crashed", error: error.message });
    });
    child.on("exit", (code, signal) => this.handleExit(code, signal));
    this.setStatus({ ...this.status, state: "starting", pid: child.pid });
  }

  async stop(): Promise<void> {
    this.stoppedByUser = true;
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    const child = this.child;
    this.rpc?.close(new Error("sidecar stopped"));
    this.rpc = null;
    this.child = null;
    if (child && !child.killed) {
      child.kill();
    }
    this.setStatus({ state: "stopped", restarts: this.status.restarts });
  }

  async reconnect(): Promise<void> {
    await this.stop();
    this.status = { state: "stopped", restarts: 0 };
    this.start();
  }

  async call(method: string, params?: JsonRpcParams): Promise<JsonValue> {
    if (!this.rpc) {
      throw new Error("sidecar is not running");
    }
    return this.rpc.call(method, params);
  }

  snapshot(): SidecarStatus {
    return { ...this.status };
  }

  markConnected(version: SidecarVersion): void {
    this.setStatus({ ...this.status, state: "connected", version, error: undefined });
  }

  markDisconnected(error: string): void {
    this.setStatus({ ...this.status, state: "disconnected", error });
  }

  private handleExit(code: number | null, signal: NodeJS.Signals | null): void {
    this.rpc?.close(new Error("sidecar exited"));
    this.rpc = null;
    this.child = null;
    if (this.stoppedByUser) {
      this.setStatus({ state: "stopped", restarts: this.status.restarts });
      return;
    }
    const restarts = this.status.restarts + 1;
    const error = `sidecar exited code=${code ?? "null"} signal=${signal ?? "null"}`;
    log.warn(error);
    if (restarts > MAX_RESTARTS) {
      this.setStatus({ state: "crashed", restarts, error });
      return;
    }
    this.setStatus({ ...this.status, state: "disconnected", restarts, error });
    this.restartTimer = setTimeout(() => this.start(), RESTART_DELAY_MS);
  }

  private setStatus(status: SidecarStatus): void {
    this.status = status;
    this.emit("status", this.snapshot());
  }
}
