import { app } from "electron";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export interface SidecarCommand {
  command: string;
  args: string[];
  cwd: string;
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..", "..", "..");

function productionBinary(): string {
  const exeName = process.platform === "win32" ? "sabi-sidecar.exe" : "sabi-sidecar";
  return join(process.resourcesPath, "sidecar", "sabi-sidecar", exeName);
}

function localBinary(): string {
  const exeName = process.platform === "win32" ? "sabi-sidecar.exe" : "sabi-sidecar";
  return join(repoRoot, "packaging", "sidecar", "dist", "sabi-sidecar", exeName);
}

export function resolveSidecarCommand(): SidecarCommand {
  const override = process.env.SABI_DESKTOP_SIDECAR_BIN;
  if (override) {
    return { command: override, args: [], cwd: repoRoot };
  }

  if (app.isPackaged) {
    return { command: productionBinary(), args: [], cwd: process.resourcesPath };
  }

  const builtBinary = localBinary();
  if (existsSync(builtBinary)) {
    return { command: builtBinary, args: [], cwd: repoRoot };
  }

  const python = process.env.SABI_DESKTOP_PYTHON || "python";
  return { command: python, args: ["-m", "sabi", "sidecar"], cwd: repoRoot };
}

export function sidecarRepoRoot(): string {
  return repoRoot;
}
