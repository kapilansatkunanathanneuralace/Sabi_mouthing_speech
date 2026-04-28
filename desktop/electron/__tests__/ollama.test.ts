import { EventEmitter } from "node:events";
import { describe, expect, it, vi, beforeEach } from "vitest";

const mocks = vi.hoisted(() => ({
  openExternal: vi.fn(),
  spawn: vi.fn(),
  spawnSync: vi.fn()
}));

vi.mock("electron", () => ({
  app: {
    isPackaged: false,
    getAppPath: () => process.cwd()
  },
  shell: {
    openExternal: mocks.openExternal
  }
}));

vi.mock("node:child_process", () => ({
  spawn: mocks.spawn,
  spawnSync: mocks.spawnSync
}));

import { OllamaManager, parseOllamaModels, readCleanupOllamaConfig } from "../ollama.js";

describe("OllamaManager", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mocks.openExternal.mockReset();
    mocks.spawn.mockReset();
    mocks.spawnSync.mockReset();
  });

  it("reads the cleanup model from the shared config", () => {
    expect(readCleanupOllamaConfig()).toMatchObject({
      baseUrl: "http://127.0.0.1:11434",
      model: "llama3.2:3b-instruct-q4_K_M"
    });
  });

  it("parses Ollama tag payloads", () => {
    expect(parseOllamaModels({ models: [{ name: "llama3" }, { model: "mistral" }] })).toEqual([
      "llama3",
      "mistral"
    ]);
  });

  it("reports ready when the CLI, API, and configured model are present", async () => {
    mocks.spawnSync.mockReturnValue({ status: 0, stdout: "C:\\Ollama\\ollama.exe\r\n" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ models: [{ name: "llama3.2:3b-instruct-q4_K_M" }] })
      }))
    );

    const status = await new OllamaManager().status();

    expect(status.ready).toBe(true);
    expect(status.cliFound).toBe(true);
    expect(status.modelPresent).toBe(true);
  });

  it("requires consent before opening the installer", async () => {
    const manager = new OllamaManager();
    await expect(manager.openInstaller()).rejects.toThrow(/consent/i);
    await expect(manager.openInstaller({ consent: true })).resolves.toMatchObject({ opened: true });
    expect(mocks.openExternal).toHaveBeenCalledWith("https://ollama.com/download");
  });

  it("runs ollama pull for the configured model with streamed progress", async () => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter;
      stderr: EventEmitter;
    };
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    mocks.spawn.mockReturnValue(child);
    const progress = vi.fn();

    const promise = new OllamaManager().pullModel({ consent: true }, progress);
    child.stdout.emit("data", Buffer.from("pulling manifest\n"));
    child.emit("close", 0);

    await expect(promise).resolves.toMatchObject({
      ok: true,
      model: "llama3.2:3b-instruct-q4_K_M",
      exitCode: 0
    });
    expect(mocks.spawn).toHaveBeenCalledWith(
      "ollama",
      ["pull", "llama3.2:3b-instruct-q4_K_M"],
      expect.objectContaining({ windowsHide: true })
    );
    expect(progress).toHaveBeenCalledWith(
      expect.objectContaining({ stream: "stdout", message: "pulling manifest\n" })
    );
  });
});
