import { chmodSync, existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

export default async function afterPack(context) {
  if (context.electronPlatformName !== "darwin") {
    return;
  }

  const identity = process.env.MAC_CODESIGN_IDENTITY || process.env.CSC_NAME;
  if (!identity) {
    console.warn("Skipping macOS sidecar deep signing: MAC_CODESIGN_IDENTITY or CSC_NAME is not set.");
    return;
  }

  const sidecarRoot = join(
    context.appOutDir,
    "Sabi.app",
    "Contents",
    "Resources",
    "sidecar",
    "sabi-sidecar"
  );
  if (!existsSync(sidecarRoot)) {
    throw new Error(`macOS sidecar tree not found: ${sidecarRoot}`);
  }

  const candidates = collectSignableFiles(sidecarRoot);
  for (const file of candidates) {
    chmodSync(file, statSync(file).mode | 0o755);
    const result = spawnSync(
      "codesign",
      [
        "--force",
        "--timestamp",
        "--options",
        "runtime",
        "--entitlements",
        "build/entitlements.mac.plist",
        "--sign",
        identity,
        file
      ],
      {
        cwd: context.packager.projectDir,
        encoding: "utf-8"
      }
    );
    if (result.status !== 0) {
      throw new Error(`codesign failed for ${file}: ${result.stderr || result.stdout}`);
    }
  }
}

function collectSignableFiles(root) {
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectSignableFiles(path));
    } else if (isSignable(path)) {
      files.push(path);
    }
  }
  files.sort((a, b) => b.length - a.length);
  return files;
}

function isSignable(path) {
  return (
    path.endsWith(".dylib")
    || path.endsWith(".so")
    || path.endsWith(".node")
    || path.endsWith(".framework")
    || path.endsWith("/sabi-sidecar")
  );
}
