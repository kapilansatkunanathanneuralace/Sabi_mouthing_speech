import { EventEmitter } from "node:events";
import type { Readable, Writable } from "node:stream";

import log from "electron-log";

import type { JsonRpcParams, JsonValue, SidecarNotification } from "./types.js";

const DEFAULT_TIMEOUT_MS = 10_000;
const LONG_RUNNING_TIMEOUT_MS = 60 * 60 * 1000;
const LONG_RUNNING_METHODS = new Set(["cache.download", "models.download_vsr"]);

interface PendingRequest {
  resolve: (value: JsonValue) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
}

export class JsonRpcClient extends EventEmitter {
  private nextId = 1;
  private pending = new Map<number, PendingRequest>();
  private buffer = "";

  constructor(
    private readonly input: Readable,
    private readonly output: Writable,
    private readonly timeoutMs = DEFAULT_TIMEOUT_MS
  ) {
    super();
    this.input.on("data", (chunk: Buffer | string) => this.handleData(chunk.toString()));
    this.input.on("close", () => this.rejectAll(new Error("sidecar stdout closed")));
    this.input.on("error", (error) => this.rejectAll(error));
  }

  call(method: string, params?: JsonRpcParams): Promise<JsonValue> {
    const id = this.nextId++;
    const payload = params === undefined ? { jsonrpc: "2.0", id, method } : { jsonrpc: "2.0", id, method, params };

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`sidecar request timed out: ${method}`));
      }, this.timeoutForMethod(method));
      this.pending.set(id, { resolve, reject, timer });
      this.output.write(`${JSON.stringify(payload)}\n`, (error) => {
        if (!error) {
          return;
        }
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      });
    });
  }

  close(error = new Error("sidecar RPC closed")): void {
    this.rejectAll(error);
    this.removeAllListeners();
  }

  private handleData(chunk: string): void {
    this.buffer += chunk;
    let newline = this.buffer.indexOf("\n");
    while (newline >= 0) {
      const line = this.buffer.slice(0, newline).trim();
      this.buffer = this.buffer.slice(newline + 1);
      if (line) {
        this.handleLine(line);
      }
      newline = this.buffer.indexOf("\n");
    }
  }

  private timeoutForMethod(method: string): number {
    if (LONG_RUNNING_METHODS.has(method) || method.startsWith("dictation.")) {
      return LONG_RUNNING_TIMEOUT_MS;
    }
    return this.timeoutMs;
  }

  private handleLine(line: string): void {
    let payload: unknown;
    try {
      payload = JSON.parse(line);
    } catch (error) {
      log.warn("Ignoring non-JSON sidecar stdout line", { line, error });
      return;
    }
    if (!payload || typeof payload !== "object") {
      return;
    }
    const message = payload as Record<string, JsonValue>;
    if ("method" in message && !("id" in message)) {
      this.emit("notification", {
        method: String(message.method),
        params: message.params
      } satisfies SidecarNotification);
      return;
    }
    const id = Number(message.id);
    const pending = this.pending.get(id);
    if (!pending) {
      return;
    }
    clearTimeout(pending.timer);
    this.pending.delete(id);
    if (message.error && typeof message.error === "object") {
      const rpcError = message.error as { message?: JsonValue; code?: JsonValue };
      pending.reject(new Error(`JSON-RPC ${rpcError.code ?? "error"}: ${rpcError.message ?? "unknown"}`));
      return;
    }
    pending.resolve(message.result ?? null);
  }

  private rejectAll(error: Error): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
      this.pending.delete(id);
    }
  }
}
