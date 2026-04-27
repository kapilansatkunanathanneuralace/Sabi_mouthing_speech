# Sabi Demo Runbook

This is the cold-start runbook for the Phase 1 internal demo: **PoC-1 silent dictation** and **PoC-2 audio dictation**. It shows Flow 1 from `project_roadmap.md`: local capture, local recognition, optional local cleanup, and paste into the focused Windows app. For simple explanations of the moving pieces, read `docs/INFRA_CHEAT_SHEET.md` first.

## Prerequisites Checklist

- Windows 10/11 laptop or desktop.
- Python 3.11 64-bit preferred. Newer Python can work, but CUDA wheels may need the fallback path in `docs/INSTALL.md`.
- `git`.
- `ffmpeg` on PATH for eval media conversion and demo recording.
- Webcam and microphone enabled for desktop apps in Windows privacy settings.
- Optional NVIDIA GPU. CPU works for setup and audio; silent VSR is much more credible on GPU.
- Optional but recommended Ollama for cleanup.
- A machine that passes `python -m sabi probe`.

Reference install doc: `docs/INSTALL.md`.

## Cold Start

Open PowerShell. Set `$RepoUrl` to the repository URL you are using, then paste the block:

```powershell
$RepoUrl = "<paste repo URL here>"
git clone $RepoUrl Sabi_MouthingSpeech
cd Sabi_MouthingSpeech
git submodule update --init --recursive

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# CUDA 12.1 track. If this fails, use the CPU fallback in docs/INSTALL.md.
pip install torch==2.3.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121

pip install -e ".[dev,eval]"
python -m sabi probe
python -m sabi download-vsr

ollama pull llama3.2:3b-instruct-q4_K_M
python -m sabi cleanup-smoke "um i think it might like work"
```

How to read `python -m sabi probe`: green rows mean that dependency or device is ready. A yellow CUDA row is acceptable for CPU-only development, but the silent VSR demo will be slower. Red camera or microphone rows must be fixed before running the live demos.

## PoC-1: Silent Dictation

Goal: mouth a sentence silently and paste text into Notepad.

1. Open Notepad and put the cursor in a blank document.
2. In PowerShell, run:

   ```powershell
   python -m sabi silent-dictate --ui tui
   ```

3. Focus Notepad again.
4. Hold **Ctrl+Alt+Space**.
5. Mouth a short phrase from `data/eval/phrases.sample.jsonl`, for example: "The birch canoe slid on the smooth planks."
6. Release **Ctrl+Alt+Space**.
7. Expect recognized text to appear in Notepad. On a healthy GPU setup the paste decision should usually happen within roughly 500 ms after release, excluding first camera-open cost.

What the TUI should show:

```text
Mode: recording -> decoding -> cleaning -> pasting -> idle
Hotkey: ctrl+alt+space
Ollama: ok llama3.2:3b-instruct-q4_K_M
CUDA: ok or unavailable
Recent utterance: text, confidence, decision, and latency columns
```

Screenshot placeholders:

- `reports/screenshots/poc1-tui-recording.png` - TUI while holding the hotkey.
- `reports/screenshots/poc1-notepad-paste.png` - Notepad after paste.

If confidence is low, the TUI may show a pending row with **F12 to paste anyway**. Press F12 within the window if the text is good enough for the demo.

## PoC-2: Audio Dictation

Goal: speak a sentence and paste text into Notepad through the audio baseline.

1. Open Notepad and put the cursor in a blank document.
2. In PowerShell, run:

   ```powershell
   python -m sabi dictate --ui tui
   ```

3. Focus Notepad again.
4. Hold **Ctrl+Alt+Space**.
5. Speak a phrase from `data/eval/phrases.sample.jsonl`.
6. Release **Ctrl+Alt+Space**.
7. Expect text to appear in Notepad. Audio is the baseline: it should usually be more accurate than silent VSR.

Useful variants:

```powershell
python -m sabi dictate --ui tui --mode push-to-talk
python -m sabi dictate --ui tui --mode vad
python -m sabi dictate --ui none --dry-run
```

Screenshot placeholders:

- `reports/screenshots/poc2-tui-recording.png` - audio TUI while recording.
- `reports/screenshots/poc2-notepad-paste.png` - Notepad after paste.

## Eval Runbook

The eval harness is offline: it reads local recordings and does not open the live webcam, microphone, hotkey, clipboard, or TUI.

Prepare a local dataset:

```powershell
mkdir data\eval\sample
copy data\eval\phrases.sample.jsonl data\eval\sample\phrases.jsonl
mkdir data\eval\sample\audio
mkdir data\eval\sample\video
```

Edit 1-3 rows in `data/eval/sample/phrases.jsonl` so `audio_path` points at `audio/<id>.wav` and `video_path` points at `video/<id>.mp4`. Use 16 kHz mono WAV files for audio. Keep actual `.wav` and `.mp4` files local; they are git-ignored.

Run audio first:

```powershell
python -m sabi eval --dataset data/eval/sample --pipeline audio --runs 1 --out reports/poc-eval-audio-test.md
```

Then run both pipelines once video clips exist:

```powershell
python -m sabi eval --dataset data/eval/sample --pipeline both --runs 1 --out reports/poc-eval-test.md
```

Interpret the report:

- **Summary**: compare raw WER and cleaned WER. Lower is better.
- **Total latency percentiles**: p50 is the median; p95 is the "bad but normal" tail.
- **Per-stage latency**: tells you whether capture, ROI, VSR/ASR, cleanup, or paste is the bottleneck.
- **Phrase Results**: shows individual phrase transcripts and decisions.
- **Known Failure Modes**: points at no-face, silence, low-confidence, empty output, or cleanup fallback cases.

## Recording The Demo

Use the helper script to record a screen-plus-webcam artifact:

```powershell
.\scripts\record_demo.ps1 -WebcamName "Integrated Camera"
```

The script writes `reports/demo-<date>.mp4`. If ffmpeg cannot find the webcam, list device names with:

```powershell
ffmpeg -list_devices true -f dshow -i dummy
```

## Known Failure Modes

| Failure mode | Observed behavior | Where to verify |
| --- | --- | --- |
| Low light or face off-center | Silent pipeline withholds paste because MediaPipe loses the face or mouth crop. | `reports/silent_dictate_YYYYMMDD.jsonl` has `decision=withheld_occluded` or `error="camera could not see your mouth"`; eval report Known Failure Modes lists no-face/occlusion. |
| Fast mouthing or strong accent | Audio stays accurate, but Chaplin VSR may diverge or produce low confidence. | Eval Phrase Results shows higher silent raw WER than audio raw WER; TUI confidence column is low. |
| Ollama unreachable | Dictation still works, but cleanup is bypassed and raw text is pasted. | TUI header shows `Ollama: offline (raw output)`; `used_fallback=true` in JSONL; eval report says `cleanup: bypassed`. |
| Target app debounces Ctrl+V | Pipeline logs a successful paste decision, but the target app misses the paste. | `reports/latency-log.md` has a normal `inject_ms`; target app has no text. Reproduce with `python -m sabi paste-test "hello world"`. |
| Clipboard manager hooks the clipboard | Paste may work, but previous clipboard contents are not restored quickly enough. | `reports/*dictate_YYYYMMDD.jsonl` shows paste success; Windows clipboard history or manager shows unexpected previous value. Tune restore delay in config if needed. |

## Known Limitations

- Windows-only PoC.
- Push-to-talk is the primary demo path.
- No audio-visual fusion yet.
- No silent meeting mode yet.
- No packaged installer.
- Single-user local setup.
- English-only prompts and evaluation examples.

## Next Steps

- **Fusion module**: combine audio and visual evidence so silent failures can be compared against the stronger audio baseline.
- **Fused dictation pipeline**: expose fusion through the same hotkey and paste UX.
- **Cleanup polish v2**: use eval reports to see whether cleanup actually lowers WER instead of just making text prettier.
- **Mode switcher**: make dictation vs meeting behavior explicit before adding more flows.
- **Edge-case hardening**: prioritize low light, clipboard contention, and target-app paste debounce because those are the failures a reviewer can see immediately.
