param(
    [string]$WebcamName = "Integrated Camera",
    [string]$OutputDir = "reports",
    [int]$FrameRate = 30,
    [string]$ScreenSize = "1440:1080",
    [string]$WebcamSize = "480:360"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "ffmpeg was not found on PATH. Install ffmpeg and reopen PowerShell."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$output = Join-Path $OutputDir "demo-$stamp.mp4"

Write-Host "Recording screen + webcam to $output"
Write-Host "Webcam device: $WebcamName"
Write-Host "Press q in the ffmpeg window, or Ctrl+C here, to stop."

ffmpeg `
    -y `
    -f gdigrab `
    -framerate $FrameRate `
    -i desktop `
    -f dshow `
    -framerate $FrameRate `
    -i "video=$WebcamName" `
    -filter_complex "[0:v]scale=$ScreenSize,setpts=PTS-STARTPTS[screen];[1:v]scale=$WebcamSize,setpts=PTS-STARTPTS[cam];[screen][cam]overlay=W-w-24:H-h-24,format=yuv420p[out]" `
    -map "[out]" `
    -r $FrameRate `
    -c:v libx264 `
    -preset veryfast `
    -crf 23 `
    -movflags +faststart `
    $output

Write-Host "Wrote $output"
