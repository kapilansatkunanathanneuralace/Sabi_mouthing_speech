import { existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(__dirname, "..");
const distRoot = join(desktopRoot, "dist");
const unpackedRoot = join(distRoot, "win-unpacked");
const maxArchiveBytes = 250 * 1024 * 1024;
const sidecarExe = join(
  unpackedRoot,
  "resources",
  "sidecar",
  "sabi-sidecar",
  "sabi-sidecar.exe"
);

if (!existsSync(distRoot)) {
  fail(`Missing dist output: ${distRoot}`);
}

const installers = readdirSync(distRoot).filter((name) => /setup\.exe$/i.test(name));
if (installers.length === 0) {
  fail("No NSIS setup executable found in desktop/dist.");
}
const installerPath = join(distRoot, installers[0]);
const embeddedArchive = readdirSync(distRoot).find((name) => name.endsWith(".nsis.7z"));
if (embeddedArchive) {
  const installerSize = statSync(installerPath).size;
  const archiveSize = statSync(join(distRoot, embeddedArchive)).size;
  if (archiveSize > maxArchiveBytes) {
    fail(
      `Installer archive exceeds 250 MB budget: ${embeddedArchive} is ${archiveSize} bytes.`
    );
  }
  if (installerSize <= archiveSize) {
    fail(
      `Installer appears incomplete: ${installers[0]} is smaller than ${embeddedArchive}.`
    );
  }
}
if (!existsSync(sidecarExe)) {
  fail(`Packaged sidecar was not found: ${sidecarExe}`);
}

const request = '{"jsonrpc":"2.0","id":1,"method":"meta.version"}\n';
const smoke = spawnSync(sidecarExe, {
  input: request,
  encoding: "utf-8",
  timeout: 15000
});
if (smoke.status !== 0) {
  fail(`Packaged sidecar smoke failed: ${smoke.stderr || smoke.stdout}`);
}
if (!smoke.stdout.includes('"protocol_version"')) {
  fail(`Unexpected sidecar smoke response: ${smoke.stdout}`);
}

const signature = signatureStatus(installerPath);
const expectSigned = process.env.WIN_EXPECT_SIGNED === "1";
if (expectSigned && signature.status !== "Valid") {
  fail(
    `Expected a valid installer signature but got ${signature.status}: `
    + `${signature.statusMessage}`
  );
}

console.log(`Installer: ${installers.join(", ")}`);
console.log("Packaged sidecar meta.version smoke passed.");
console.log(`Installer signature: ${signature.status} - ${signature.statusMessage}`);

function fail(message) {
  console.error(message);
  process.exit(1);
}

function signatureStatus(filePath) {
  if (process.platform !== "win32") {
    return { status: "Skipped", statusMessage: "Authenticode validation requires Windows." };
  }
  const command = [
    "$sig = Get-AuthenticodeSignature -LiteralPath $env:SABI_INSTALLER_TO_VALIDATE;",
    "[pscustomobject]@{Status=[string]$sig.Status;StatusMessage=$sig.StatusMessage}",
    "| ConvertTo-Json -Compress"
  ].join(" ");
  const result = spawnSync(
    "powershell",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
    {
      encoding: "utf-8",
      env: { ...process.env, SABI_INSTALLER_TO_VALIDATE: filePath }
    }
  );
  if (result.status !== 0) {
    return {
      status: "Unknown",
      statusMessage: result.stderr.trim() || "PowerShell signature validation failed."
    };
  }
  try {
    const parsed = JSON.parse(result.stdout);
    return {
      status: parsed.Status ?? parsed.status ?? "Unknown",
      statusMessage: parsed.StatusMessage ?? parsed.statusMessage ?? ""
    };
  } catch {
    return {
      status: "Unknown",
      statusMessage: result.stdout.trim() || "Could not parse signature validation output."
    };
  }
}
