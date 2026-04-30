import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

if (process.platform !== "darwin") {
  console.error("macOS packaging must run on a macOS host.");
  process.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(__dirname, "..");
const repoRoot = resolve(desktopRoot, "..");
const requestedArch = process.argv.includes("--x64")
  ? "x64"
  : process.argv.includes("--arm64")
    ? "arm64"
    : process.env.SABI_MAC_ARCH || process.arch;
if (!["x64", "arm64"].includes(requestedArch)) {
  console.error(`Unsupported macOS package architecture: ${requestedArch}`);
  process.exit(1);
}
const sidecarBin = join(
  repoRoot,
  "packaging",
  "sidecar",
  "release-dist",
  "sabi-sidecar",
  "sabi-sidecar"
);

if (!existsSync(sidecarBin)) {
  console.error(`Missing macOS sidecar binary: ${sidecarBin}`);
  console.error("Run from the repo root first on macOS: python scripts/build_sidecar_release.py");
  process.exit(1);
}

const electronBuilder = join(desktopRoot, "node_modules", ".bin", "electron-builder");
const args = ["--mac", "dmg", "zip", `--${requestedArch}`, "--config", "build/electron-builder.yml"];
const result = spawnSync(electronBuilder, args, {
  cwd: desktopRoot,
  env: process.env,
  stdio: "inherit"
});

process.exit(result.status ?? 1);
