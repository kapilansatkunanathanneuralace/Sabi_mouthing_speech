import { existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(__dirname, "..");
const repoRoot = resolve(desktopRoot, "..");
const sidecarExe = join(
  repoRoot,
  "packaging",
  "sidecar",
  "release-dist",
  "sabi-sidecar",
  "sabi-sidecar.exe"
);

if (!existsSync(sidecarExe)) {
  console.error(`Missing sidecar binary: ${sidecarExe}`);
  console.error("Run from the repo root first: python scripts/build_sidecar_release.py");
  process.exit(1);
}

const isLocalSelfSignedBuild = process.env.WIN_SELF_SIGNED_LOCAL === "1";
const localSelfSignedCertPath = process.env.WIN_CSC_LINK;
const localSelfSignedCertPassword = process.env.WIN_CSC_KEY_PASSWORD;
if (!isLocalSelfSignedBuild && process.env.WIN_CSC_LINK && !process.env.CSC_LINK) {
  process.env.CSC_LINK = process.env.WIN_CSC_LINK;
}
if (
  !isLocalSelfSignedBuild
  && process.env.WIN_CSC_KEY_PASSWORD
  && !process.env.CSC_KEY_PASSWORD
) {
  process.env.CSC_KEY_PASSWORD = process.env.WIN_CSC_KEY_PASSWORD;
}
if (isLocalSelfSignedBuild) {
  delete process.env.CSC_LINK;
  delete process.env.CSC_KEY_PASSWORD;
  delete process.env.WIN_CSC_LINK;
  delete process.env.WIN_CSC_KEY_PASSWORD;
}
const isUnsignedLocalBuild = !process.env.CSC_LINK && !process.env.WIN_AZURE_SIGNING;
if (isUnsignedLocalBuild) {
  process.env.CSC_IDENTITY_AUTO_DISCOVERY = "false";
  if (isLocalSelfSignedBuild) {
    console.log("Producing unsigned package before local self-signing step.");
  } else {
    console.warn("No Windows signing env vars found; producing an unsigned local installer.");
  }
} else if (process.env.CSC_LINK) {
  console.log(`Using Windows signing certificate from ${process.env.CSC_LINK}.`);
} else {
  console.log("Using Azure Trusted Signing configuration.");
}

const electronBuilder = join(
  desktopRoot,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "electron-builder.cmd" : "electron-builder"
);
const args = ["--win", "nsis", "--x64", "--config", "build/electron-builder.yml"];
if (isUnsignedLocalBuild) {
  args.push("--config.win.signAndEditExecutable=false");
}

const result = spawnSync(electronBuilder, args, {
  cwd: desktopRoot,
  env: process.env,
  shell: process.platform === "win32",
  stdio: "inherit"
});

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

if (isLocalSelfSignedBuild) {
  signInstallerLocally();
}

process.exit(0);

function signInstallerLocally() {
  if (!localSelfSignedCertPath || !localSelfSignedCertPassword) {
    console.error("WIN_SELF_SIGNED_LOCAL requires WIN_CSC_LINK and WIN_CSC_KEY_PASSWORD.");
    process.exit(1);
  }
  const distRoot = join(desktopRoot, "dist");
  const installer = readdirSync(distRoot).find((name) => /setup\.exe$/i.test(name));
  if (!installer) {
    console.error(`No setup executable found in ${distRoot}.`);
    process.exit(1);
  }
  const installerPath = join(distRoot, installer);
  const command = [
    "$password = ConvertTo-SecureString $env:WIN_CSC_KEY_PASSWORD -AsPlainText -Force;",
    "$cert = Import-PfxCertificate -FilePath $env:WIN_CSC_LINK",
    "-CertStoreLocation Cert:\\CurrentUser\\My -Password $password;",
    "Set-AuthenticodeSignature -FilePath $env:SABI_INSTALLER_TO_SIGN -Certificate $cert",
    "-HashAlgorithm SHA256 | Format-List Status,StatusMessage"
  ].join(" ");
  const sign = spawnSync(
    "powershell",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
    {
      cwd: desktopRoot,
      env: {
        ...process.env,
        WIN_CSC_LINK: localSelfSignedCertPath,
        WIN_CSC_KEY_PASSWORD: localSelfSignedCertPassword,
        SABI_INSTALLER_TO_SIGN: installerPath
      },
      stdio: "inherit"
    }
  );
  if (sign.status !== 0) {
    process.exit(sign.status ?? 1);
  }
}
