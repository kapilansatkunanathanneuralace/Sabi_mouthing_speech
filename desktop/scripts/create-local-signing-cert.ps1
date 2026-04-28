param(
    [string]$CertDir = ".certs",
    [string]$PfxName = "sabi-local-test-signing.pfx",
    [string]$Subject = "CN=Sabi Local Test Signing",
    [string]$Password = $env:WIN_CSC_KEY_PASSWORD,
    [switch]$Trust
)

$ErrorActionPreference = "Stop"

if (-not $Password) {
    $securePrompt = Read-Host "PFX password" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePrompt)
    try {
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopRoot = Resolve-Path (Join-Path $scriptRoot "..")
$certRoot = Join-Path $desktopRoot $CertDir
New-Item -ItemType Directory -Force -Path $certRoot | Out-Null

$pfxPath = Join-Path $certRoot $PfxName
$cerPath = [System.IO.Path]::ChangeExtension($pfxPath, ".cer")
$securePassword = ConvertTo-SecureString -String $Password -AsPlainText -Force

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyAlgorithm RSA `
    -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -KeyExportPolicy Exportable `
    -KeyUsage DigitalSignature `
    -NotAfter (Get-Date).AddYears(2)

Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $securePassword | Out-Null
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

if ($Trust) {
    Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\TrustedPublisher" | Out-Null
    Import-Certificate -FilePath $cerPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
}

Write-Host "Created local test signing certificate:"
Write-Host "  Subject: $Subject"
Write-Host "  Thumbprint: $($cert.Thumbprint)"
Write-Host "  PFX: $pfxPath"
Write-Host ""
Write-Host "Set these environment variables before packaging:"
Write-Host "  `$env:WIN_CSC_LINK = `"$pfxPath`""
Write-Host "  `$env:WIN_CSC_KEY_PASSWORD = `"$Password`""
Write-Host ""
Write-Host "This certificate is for local developer validation only. Do not use it for releases."
if (-not $Trust) {
    Write-Host "Run again with -Trust to trust it in CurrentUser stores for local signature validation."
}
