import { app } from "electron";
import { createHash } from "node:crypto";
import {
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync
} from "node:fs";
import { copyFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

export type RuntimeState = "missing" | "available" | "installed" | "corrupt" | "unsupported";

export interface RuntimeManifest {
  name: string;
  version: string;
  platform: string;
  arch: string;
  min_desktop_version: string;
  url: string;
  sha256: string;
  size_bytes: number;
  artifact: string;
  sidecar_dir: string;
  description: string;
}

export interface RuntimeStatus {
  state: RuntimeState;
  root: string;
  active_dir: string;
  sidecar_bin: string;
  manifest: RuntimeManifest;
  message?: string;
}

export interface RuntimeDownloadParams {
  url?: string;
  path?: string;
  force?: boolean;
}

const RUNTIME_ID = "full-cpu";
const MANIFEST_NAME = "full-cpu.json";

function runtimeManifestNames(): string[] {
  const platformAlias = process.platform === "darwin" ? "macos" : process.platform === "win32" ? "win" : process.platform;
  return [
    `full-cpu-${platformAlias}-${process.arch}.json`,
    `full-cpu-${process.platform}-${process.arch}.json`,
    MANIFEST_NAME
  ];
}

function sidecarExecutableName(): string {
  return process.platform === "win32" ? "sabi-sidecar.exe" : "sabi-sidecar";
}

function appDataRoot(): string {
  if (process.platform === "win32") {
    return join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "Sabi");
  }
  if (process.platform === "darwin") {
    return join(homedir(), "Library", "Application Support", "Sabi");
  }
  return join(process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"), "sabi");
}

export function runtimeRoot(): string {
  return join(appDataRoot(), "runtime", RUNTIME_ID);
}

export function activeRuntimeDir(): string {
  return join(runtimeRoot(), "current");
}

export function activeRuntimeBinary(): string {
  return join(activeRuntimeDir(), "sabi-sidecar", sidecarExecutableName());
}

export function activeRuntimeCwd(): string {
  return activeRuntimeDir();
}

export function hasActiveRuntime(): boolean {
  return existsSync(activeRuntimeBinary());
}

export class RuntimeManager {
  status(): RuntimeStatus {
    const manifest = this.readManifest();
    const sidecar = activeRuntimeBinary();
    if (manifest.platform !== process.platform) {
      return this.statusWith("unsupported", manifest, `Runtime platform ${manifest.platform} does not match ${process.platform}.`);
    }
    if (!existsSync(sidecar)) {
      const source = this.runtimeSource(manifest);
      return this.statusWith(source ? "available" : "missing", manifest);
    }
    try {
      const installed = JSON.parse(
        readFileSync(join(activeRuntimeDir(), "runtime-pack.json"), "utf-8")
      ) as RuntimeManifest;
      if (installed.name !== manifest.name) {
        return this.statusWith("corrupt", manifest, "Installed runtime metadata does not match.");
      }
      return this.statusWith("installed", manifest);
    } catch {
      return this.statusWith("corrupt", manifest, "Installed runtime metadata is missing.");
    }
  }

  async download(params: RuntimeDownloadParams = {}): Promise<RuntimeStatus> {
    const manifest = this.readManifest();
    const source = this.runtimeSource(manifest, params);
    if (!source) {
      return this.statusWith(
        "missing",
        manifest,
        "No full runtime pack URL configured. Build one with scripts/build_sidecar_full_cpu.py or set SABI_FULL_RUNTIME_ZIP."
      );
    }
    mkdirSync(join(runtimeRoot(), "downloads"), { recursive: true });
    const archive = join(runtimeRoot(), "downloads", basename(source));
    if (source.startsWith("http://") || source.startsWith("https://")) {
      await this.downloadUrl(source, archive);
    } else if (source.startsWith("file://")) {
      await copyFile(new URL(source), archive);
    } else {
      await copyFile(source, archive);
    }
    await this.verifyArchive(archive, manifest);
    this.extractArchive(archive, manifest);
    return this.status();
  }

  verify(): RuntimeStatus {
    return this.status();
  }

  clear(): RuntimeStatus {
    rmSync(runtimeRoot(), { recursive: true, force: true });
    return this.status();
  }

  private readManifest(): RuntimeManifest {
    const runtimeDir = app.isPackaged
      ? join(process.resourcesPath, "runtime")
      : join(dirname(app.getAppPath()), "configs", "runtime");
    const packagedManifest = runtimeManifestNames()
      .map((name) => join(runtimeDir, name))
      .find((candidate) => existsSync(candidate));
    if (!packagedManifest) {
      throw new Error(`No runtime manifest found in ${runtimeDir}`);
    }
    return JSON.parse(readFileSync(packagedManifest, "utf-8")) as RuntimeManifest;
  }

  private statusWith(
    state: RuntimeState,
    manifest: RuntimeManifest,
    message?: string
  ): RuntimeStatus {
    return {
      state,
      root: runtimeRoot(),
      active_dir: activeRuntimeDir(),
      sidecar_bin: activeRuntimeBinary(),
      manifest,
      message
    };
  }

  private runtimeSource(manifest: RuntimeManifest, params: RuntimeDownloadParams = {}): string {
    if (params.path) {
      return params.path;
    }
    if (params.url) {
      return params.url;
    }
    if (process.env.SABI_FULL_RUNTIME_ZIP) {
      return process.env.SABI_FULL_RUNTIME_ZIP;
    }
    return manifest.url;
  }

  private async downloadUrl(url: string, dest: string): Promise<void> {
    const response = await fetch(url);
    if (!response.ok || !response.body) {
      throw new Error(`runtime download failed: ${response.status} ${response.statusText}`);
    }
    const body = Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0]);
    await pipeline(body, createWriteStream(dest));
  }

  private async verifyArchive(path: string, manifest: RuntimeManifest): Promise<void> {
    if (!manifest.sha256) {
      return;
    }
    const digest = createHash("sha256");
    await new Promise<void>((resolve, reject) => {
      const stream = createReadStream(path);
      stream.on("data", (chunk) => digest.update(chunk));
      stream.on("error", reject);
      stream.on("end", resolve);
    });
    const actual = digest.digest("hex");
    if (actual.toLowerCase() !== manifest.sha256.toLowerCase()) {
      throw new Error(`runtime sha256 mismatch: expected ${manifest.sha256}, got ${actual}`);
    }
  }

  private extractArchive(path: string, manifest: RuntimeManifest): void {
    const staging = join(runtimeRoot(), "staging");
    rmSync(staging, { recursive: true, force: true });
    mkdirSync(staging, { recursive: true });
    if (process.platform === "win32") {
      this.extractArchiveWindows(path, staging);
    } else if (process.platform === "darwin") {
      this.extractArchiveMac(path, staging);
    } else {
      throw new Error(`runtime pack extraction is not implemented for ${process.platform}`);
    }
    const extractedSidecar = join(staging, manifest.sidecar_dir, sidecarExecutableName());
    if (!existsSync(extractedSidecar)) {
      throw new Error(`runtime pack missing sidecar binary: ${extractedSidecar}`);
    }
    this.activateStagedRuntime(staging, manifest);
  }

  private extractArchiveWindows(path: string, staging: string): void {
    const result = spawnSync(
      "powershell",
      [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Expand-Archive -LiteralPath $env:SABI_RUNTIME_ARCHIVE -DestinationPath $env:SABI_RUNTIME_STAGING -Force"
      ],
      {
        env: {
          ...process.env,
          SABI_RUNTIME_ARCHIVE: path,
          SABI_RUNTIME_STAGING: staging
        },
        encoding: "utf-8"
      }
    );
    if (result.status !== 0) {
      throw new Error(result.stderr || "runtime extraction failed");
    }
  }

  private extractArchiveMac(path: string, staging: string): void {
    const result = spawnSync("ditto", ["-x", "-k", path, staging], {
      encoding: "utf-8"
    });
    if (result.status !== 0) {
      throw new Error(result.stderr || "runtime extraction failed");
    }
    spawnSync("xattr", ["-dr", "com.apple.quarantine", staging], {
      encoding: "utf-8"
    });
  }

  private activateStagedRuntime(staging: string, manifest: RuntimeManifest): void {
    rmSync(activeRuntimeDir(), { recursive: true, force: true });
    mkdirSync(dirname(activeRuntimeDir()), { recursive: true });
    if (process.platform !== "win32") {
      renameSync(staging, activeRuntimeDir());
      this.writeRuntimeMetadata(manifest);
      return;
    }
    const move = spawnSync(
      "powershell",
      [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Move-Item -LiteralPath $env:SABI_RUNTIME_STAGING -Destination $env:SABI_RUNTIME_ACTIVE -Force"
      ],
      {
        env: {
          ...process.env,
          SABI_RUNTIME_STAGING: staging,
          SABI_RUNTIME_ACTIVE: activeRuntimeDir()
        },
        encoding: "utf-8"
      }
    );
    if (move.status !== 0) {
      throw new Error(move.stderr || "runtime activation failed");
    }
    this.writeRuntimeMetadata(manifest);
  }

  private writeRuntimeMetadata(manifest: RuntimeManifest): void {
    writeFileSync(
      join(activeRuntimeDir(), "runtime-pack.json"),
      JSON.stringify(manifest, null, 2) + "\n",
      "utf-8"
    );
  }
}
