# Windows Signing

TICKET-049 packages Sabi with electron-builder and NSIS. Local developer builds may
be unsigned, but release builds must be Authenticode signed before distribution.

## Certificate Options

- EV certificate: best SmartScreen outcome for public releases because reputation is
  hardware-backed and usually trusted faster.
- OV certificate: acceptable for early/internal channels, but fresh certificates can
  show SmartScreen warnings for days or weeks while reputation builds.
- Azure Trusted Signing: a good CI-friendly option when the account and identity
  validation are already in place.

## Local Env Vars

The package wrapper accepts Sabi-specific env vars and maps them to electron-builder's
standard signing variables:

```powershell
$env:WIN_CSC_LINK = "C:\secrets\sabi-signing.pfx"
$env:WIN_CSC_KEY_PASSWORD = "<pfx password>"
cd desktop
npm run package:win
```

If `WIN_CSC_LINK` is not present, `npm run package:win` disables certificate auto
discovery and executable signing/editing for unsigned local smoke builds.

Electron-builder also supports the standard `CSC_LINK` and `CSC_KEY_PASSWORD`
variables directly. CI can set either pair, but release jobs should prefer one naming
scheme and document it in the workflow.

## Self-Signed Local Test Certificate

For developer validation on a Windows machine, create a local code-signing certificate:

```powershell
cd desktop
npm run signing:create-local-cert -- -Trust
```

The helper writes a password-protected PFX under `desktop/.certs/`, which is ignored
by Git. The `-Trust` flag imports the public certificate into the current user's
`TrustedPublisher` and `Root` stores so `Get-AuthenticodeSignature` can report
`Valid` on that same machine. This does not create public trust and does not improve
SmartScreen reputation.

Set the printed env vars before packaging:

```powershell
$env:WIN_CSC_LINK = ".certs\sabi-local-test-signing.pfx"
$env:WIN_CSC_KEY_PASSWORD = "<pfx password>"
$env:WIN_SELF_SIGNED_LOCAL = "1"
$env:WIN_EXPECT_SIGNED = "1"
npm run package:win
npm run validate:win-package
```

`WIN_SELF_SIGNED_LOCAL=1` packages without electron-builder's signing toolchain and
then signs the generated setup executable with PowerShell. This avoids local
permission issues when electron-builder downloads and extracts its Windows signing
tools. `WIN_EXPECT_SIGNED=1` makes validation fail unless the setup executable has a
valid Authenticode signature on the local machine.

To remove the local test certificate later:

```powershell
$thumbprint = "<thumbprint printed by the helper>"
Remove-Item "Cert:\CurrentUser\My\$thumbprint" -ErrorAction SilentlyContinue
Remove-Item "Cert:\CurrentUser\TrustedPublisher\$thumbprint" -ErrorAction SilentlyContinue
Remove-Item "Cert:\CurrentUser\Root\$thumbprint" -ErrorAction SilentlyContinue
Remove-Item ".certs" -Recurse -Force
```

Never reuse the self-signed certificate for public distribution.

## CI Plan

1. Build the PyInstaller sidecar on a Windows x64 runner with `python scripts/build_sidecar_release.py`.
2. Install desktop dependencies with Node 20 LTS.
3. Set signing secrets (`WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD`) or Azure Trusted
   Signing configuration.
4. Run `npm run package:win`.
5. Verify the installer signature and archive the setup executable.

## Verify Signatures

```powershell
Get-AuthenticodeSignature .\desktop\dist\Sabi-0.0.1-setup.exe | Format-List
```

Expected release result:

- `Status` is `Valid`.
- `SignerCertificate.Subject` matches the Sabi publisher certificate.
- Timestamp information is present so the signature remains valid after certificate
  expiration.

Unsigned local smoke builds are acceptable only for development validation. They do
not satisfy the signed-release acceptance criterion.
