import { existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

if (process.platform !== "darwin") {
  console.error("macOS package validation must run on a macOS host.");
  process.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(__dirname, "..");
const distRoot = join(desktopRoot, "dist");

if (!existsSync(distRoot)) {
  fail(`Missing dist output: ${distRoot}`);
}

const artifacts = readdirSync(distRoot);
const dmgArtifacts = artifacts.filter((name) => name.endsWith(".dmg"));
const zipArtifacts = artifacts.filter((name) => name.endsWith(".zip"));
if (dmgArtifacts.length === 0) {
  fail("No macOS DMG artifacts found in desktop/dist.");
}
if (zipArtifacts.length === 0) {
  fail("No macOS ZIP artifacts found in desktop/dist.");
}

const appCandidates = [
  join(distRoot, "mac-arm64", "Sabi.app"),
  join(distRoot, "mac", "Sabi.app"),
  join(distRoot, "mac-x64", "Sabi.app")
].filter((candidate) => existsSync(candidate));

if (appCandidates.length === 0) {
  fail("No unpacked Sabi.app found under desktop/dist/mac*.");
}

for (const appPath of appCandidates) {
  const sidecarBin = join(appPath, "Contents", "Resources", "sidecar", "sabi-sidecar", "sabi-sidecar");
  const runtimeManifest = join(appPath, "Contents", "Resources", "runtime", "full-cpu.json");
  if (!existsSync(sidecarBin)) {
    fail(`Packaged macOS sidecar was not found: ${sidecarBin}`);
  }
  if (!existsSync(runtimeManifest)) {
    fail(`Runtime manifest was not found: ${runtimeManifest}`);
  }
  const smoke = spawnSync(sidecarBin, {
    input: '{"jsonrpc":"2.0","id":1,"method":"meta.version"}\n',
    encoding: "utf-8",
    timeout: 15000
  });
  if (smoke.status !== 0 || !smoke.stdout.includes('"protocol_version"')) {
    fail(`Packaged sidecar smoke failed for ${appPath}: ${smoke.stderr || smoke.stdout}`);
  }
  const spctl = spawnSync("spctl", ["--assess", "--type", "execute", "-v", appPath], {
    encoding: "utf-8"
  });
  console.log(`${appPath}: spctl ${spctl.status === 0 ? "accepted" : "failed"}`);
  if (spctl.status !== 0) {
    console.log(spctl.stderr.trim() || spctl.stdout.trim());
  }
}

console.log(`DMG artifacts: ${dmgArtifacts.join(", ")}`);
console.log(`ZIP artifacts: ${zipArtifacts.join(", ")}`);
console.log("Packaged macOS sidecar meta.version smoke passed.");

function fail(message) {
  console.error(message);
  process.exit(1);
}
