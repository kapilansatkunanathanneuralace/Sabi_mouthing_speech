import { app, shell } from "electron";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

const DEFAULT_BASE_URL = "http://127.0.0.1:11434";
const DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M";
const INSTALLER_URL = "https://ollama.com/download";

export interface OllamaStatus {
  cliFound: boolean;
  cliPath?: string;
  apiReachable: boolean;
  baseUrl: string;
  model: string;
  modelPresent: boolean;
  installed: boolean;
  ready: boolean;
  detail: string;
  models: string[];
}

export interface OllamaProgress {
  model: string;
  stream: "stdout" | "stderr" | "status";
  message: string;
}

export interface OllamaPullParams {
  consent?: boolean;
}

export interface OllamaPullResult {
  ok: boolean;
  model: string;
  exitCode: number | null;
}

interface CleanupOllamaConfig {
  baseUrl: string;
  model: string;
}

export class OllamaManager {
  private activePull = false;

  async status(): Promise<OllamaStatus> {
    const config = readCleanupOllamaConfig();
    const cliPath = findOllamaCli();
    const tagResult = await fetchTags(config.baseUrl);
    const models = tagResult.models;
    const modelPresent = models.includes(config.model);
    const apiReachable = tagResult.ok;
    const cliFound = Boolean(cliPath);

    return {
      cliFound,
      cliPath,
      apiReachable,
      baseUrl: config.baseUrl,
      model: config.model,
      modelPresent,
      installed: cliFound || apiReachable,
      ready: apiReachable && modelPresent,
      detail: statusDetail({ apiReachable, cliFound, model: config.model, modelPresent }),
      models
    };
  }

  async openInstaller(
    params: { consent?: boolean } = {}
  ): Promise<{ opened: boolean; url: string }> {
    if (!params.consent) {
      throw new Error("User consent is required before opening the Ollama installer.");
    }
    await shell.openExternal(INSTALLER_URL);
    return { opened: true, url: INSTALLER_URL };
  }

  async pullModel(
    params: OllamaPullParams = {},
    onProgress?: (progress: OllamaProgress) => void
  ): Promise<OllamaPullResult> {
    if (!params.consent) {
      throw new Error(
        "User consent is required before downloading an Ollama model."
      );
    }
    if (this.activePull) {
      throw new Error("An Ollama model pull is already running.");
    }

    const { model } = readCleanupOllamaConfig();
    this.activePull = true;
    onProgress?.({ model, stream: "status", message: `Starting ollama pull ${model}` });

    return await new Promise((resolve, reject) => {
      const child = spawn("ollama", ["pull", model], {
        env: process.env,
        windowsHide: true
      });

      child.stdout?.on("data", (chunk: Buffer) => {
        onProgress?.({ model, stream: "stdout", message: chunk.toString("utf-8") });
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        onProgress?.({ model, stream: "stderr", message: chunk.toString("utf-8") });
      });
      child.on("error", (error) => {
        this.activePull = false;
        reject(error);
      });
      child.on("close", (exitCode) => {
        this.activePull = false;
        onProgress?.({
          model,
          stream: "status",
          message: exitCode === 0 ? "Ollama model pull completed." : `Ollama model pull exited with ${exitCode}.`
        });
        resolve({ ok: exitCode === 0, model, exitCode });
      });
    });
  }
}

export function readCleanupOllamaConfig(): CleanupOllamaConfig {
  const path = cleanupConfigPath();
  if (!existsSync(path)) {
    return { baseUrl: DEFAULT_BASE_URL, model: DEFAULT_MODEL };
  }
  const data = readFileSync(path, "utf-8");
  const ollama = parseTomlSection(data, "ollama");
  return {
    baseUrl: ollama.base_url ?? DEFAULT_BASE_URL,
    model: ollama.model ?? DEFAULT_MODEL
  };
}

export function parseOllamaModels(payload: unknown): string[] {
  if (!payload || typeof payload !== "object" || !("models" in payload)) {
    return [];
  }
  const models = (payload as { models?: unknown }).models;
  if (!Array.isArray(models)) {
    return [];
  }
  return models
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const record = item as { name?: unknown; model?: unknown };
      const name = typeof record.name === "string" ? record.name : record.model;
      return typeof name === "string" ? name : null;
    })
    .filter((name): name is string => Boolean(name));
}

function cleanupConfigPath(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, "configs", "cleanup.toml");
  }
  return join(dirname(app.getAppPath()), "configs", "cleanup.toml");
}

function parseTomlSection(data: string, section: string): Record<string, string> {
  const values: Record<string, string> = {};
  let active = false;
  for (const rawLine of data.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const header = line.match(/^\[([^\]]+)]$/);
    if (header) {
      active = header[1] === section;
      continue;
    }
    if (!active) {
      continue;
    }
    const match = line.match(/^([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"$/);
    if (match) {
      values[match[1]] = match[2];
    }
  }
  return values;
}

function findOllamaCli(): string | undefined {
  const command = process.platform === "win32" ? "where.exe" : "which";
  const result = spawnSync(command, ["ollama"], { encoding: "utf-8", windowsHide: true });
  if (result.status !== 0) {
    return undefined;
  }
  return result.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
}

async function fetchTags(baseUrl: string): Promise<{ ok: boolean; models: string[] }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 750);
  try {
    const response = await fetch(new URL("/api/tags", baseUrl), { signal: controller.signal });
    if (!response.ok) {
      return { ok: false, models: [] };
    }
    return { ok: true, models: parseOllamaModels(await response.json()) };
  } catch {
    return { ok: false, models: [] };
  } finally {
    clearTimeout(timeout);
  }
}

function statusDetail({
  apiReachable,
  cliFound,
  model,
  modelPresent
}: {
  apiReachable: boolean;
  cliFound: boolean;
  model: string;
  modelPresent: boolean;
}): string {
  if (apiReachable && modelPresent) {
    return `Ollama is ready with ${model}.`;
  }
  if (apiReachable) {
    return `Ollama is running, but ${model} has not been pulled yet.`;
  }
  if (cliFound) {
    return "Ollama is installed, but the local API is not reachable yet.";
  }
  return "Ollama is not installed or is not on PATH.";
}
