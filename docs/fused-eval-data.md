# Fused Eval Data Collection

This guide fills `data/eval/fused/` with paired webcam video and microphone audio for
the fused dictation eval harness. This is evaluation data, not training data: the
current ASR, VSR, fusion, and cleanup models do not automatically learn from these
files. The dataset tells us how well the current pipeline works for your face,
camera, microphone, room, and speaking style.

## Output Layout

The collector writes:

```text
data/eval/fused/
  phrases.jsonl
  video/
    harvard_001.mp4
  audio/
    harvard_001.wav
```

Each `phrases.jsonl` row uses relative paths so the folder can move as a unit:

```json
{"id":"harvard_001","text":"The birch canoe slid on the smooth planks.","video_path":"video/harvard_001.mp4","audio_path":"audio/harvard_001.wav","tags":["harvard","fused"]}
```

## Before Recording

Install or verify `ffmpeg`:

```powershell
ffmpeg -version
```

List Windows camera and microphone device names:

```powershell
ffmpeg -list_devices true -f dshow -i dummy
```

Copy the exact camera and microphone names from the output. Names often contain
spaces and parentheses, so quote them in PowerShell.

Use good capture conditions:

- Face the camera directly, with your mouth visible.
- Use bright, even lighting; avoid strong backlight.
- Keep the camera stable and avoid covering your mouth.
- Speak the phrase naturally and clearly.
- Keep background noise low so the audio baseline is fair.

## Dry Run

Check which files will be created before touching the camera or microphone:

```powershell
python -m sabi collect-fused-eval --dry-run --limit 1
```

This prints planned `video_path` and `audio_path` values but does not create media
or update `phrases.jsonl`.

## Record One Phrase

```powershell
python -m sabi collect-fused-eval `
  --limit 1 `
  --camera-name "Integrated Camera" `
  --mic-name "Microphone Array (Realtek(R) Audio)"
```

The command shows the phrase, counts down, records for the configured duration,
validates the MP4/WAV pair, and updates `data/eval/fused/phrases.jsonl`.

By default each phrase records for 4 seconds. Use `--duration-s` when a phrase is
longer:

```powershell
python -m sabi collect-fused-eval --limit 1 --duration-s 6 `
  --camera-name "Integrated Camera" `
  --mic-name "Microphone Array (Realtek(R) Audio)"
```

## Continue Or Retry

Skip media that already exists and continue filling the dataset:

```powershell
python -m sabi collect-fused-eval --skip-existing `
  --camera-name "Integrated Camera" `
  --mic-name "Microphone Array (Realtek(R) Audio)"
```

Re-record a specific phrase:

```powershell
python -m sabi collect-fused-eval --retry harvard_001 `
  --camera-name "Integrated Camera" `
  --mic-name "Microphone Array (Realtek(R) Audio)"
```

Collect a subset:

```powershell
python -m sabi collect-fused-eval --start-at harvard_010 --limit 5 `
  --camera-name "Integrated Camera" `
  --mic-name "Microphone Array (Realtek(R) Audio)"
```

## Validate And Evaluate

After collecting, run fused eval:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md
```

To compare cleanup prompts on the same personal dataset:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --cleanup-prompt v1,v2 --out reports/poc-eval-fused-personal-ab.md
```

The report measures WER, per-stage latency, confidence, and failure modes for the
current pipeline. If results are poor, the next action is manual tuning or code
changes: adjust fusion thresholds, improve capture conditions, inspect ASR/VSR
outputs, or later add a true fine-tuning ticket. There is no command to make this
data "take effect" as training in the current PoC.

## Privacy And Git

The MP4/WAV files contain your face and voice. Keep them local unless you
explicitly decide to share them. Media under `data/eval/**` should stay out of git;
only small sample metadata should be committed.
