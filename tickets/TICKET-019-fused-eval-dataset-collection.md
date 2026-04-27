# TICKET-019 - Fused eval dataset collection tool

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: M
Depends on: TICKET-014, TICKET-017
Status: Done

## Goal

Build a guided data-collection tool that records synchronized webcam video and microphone audio for the fused dictation eval harness. The tool should make it easy for one person to fill `data/eval/fused/` with usable `video_path` / `audio_path` pairs and an updated `phrases.jsonl`, without manually running ffmpeg or hand-editing JSONL.

## System dependencies

- Working webcam and microphone.
- `ffmpeg` available on PATH for robust synchronized capture and WAV conversion.
- Windows 10/11. The first implementation may use Windows-specific ffmpeg devices; cross-platform collection is out of scope.

## Python packages

Already installed:

- `typer` / `rich` for the CLI prompts and progress output.
- `opencv-python` for post-capture video validation.
- Python `wave` module for WAV validation.

No additions.

## Work

- Create `src/sabi/eval/collect_fused.py`.
- Define `FusedEvalCollectionConfig` with:
  - `out_dir = data/eval/fused`
  - `phrases_path = data/eval/phrases.sample.jsonl`
  - `video_dir = video`
  - `audio_dir = audio`
  - `video_ext = mp4`
  - `audio_sample_rate = 16000`
  - optional `camera_name`, `mic_name`, `duration_s`, and `overwrite` fields.
- Add `python -m sabi collect-fused-eval` CLI:
  - Loads phrase rows from an existing JSONL/JSON phrase file.
  - Shows one phrase at a time with phrase id, text, and progress count.
  - Gives the user a short countdown before recording.
  - Records webcam video and microphone audio for the same take.
  - Writes `video/<phrase_id>.mp4` and `audio/<phrase_id>.wav`.
  - Writes or updates `phrases.jsonl` with relative paths suitable for `python -m sabi eval --pipeline fused`.
  - Supports `--limit`, `--start-at`, `--phrase-id`, `--retry`, `--skip-existing`, and `--dry-run`.
- Validate every captured pair:
  - Video opens with OpenCV and contains at least one frame.
  - Audio is 16 kHz, 16-bit PCM, mono WAV.
  - Duration is non-zero and roughly matches the requested take duration.
- Add a README-style collection guide in `docs/fused-eval-data.md`.
- Add unit tests for phrase loading, path generation, JSONL writing, validation, skip/retry behavior, and dry-run behavior without touching real hardware.

## Acceptance criteria

- [x] `python -m sabi collect-fused-eval --help` documents output paths, phrase source, device overrides, and retry/skip flags.
- [x] Running the tool for one phrase creates `data/eval/fused/video/<id>.mp4`, `data/eval/fused/audio/<id>.wav`, and a `data/eval/fused/phrases.jsonl` row with relative paths.
- [x] Captured WAVs are mono, 16 kHz, 16-bit PCM and load through `load_wav_utterance()`.
- [x] Captured MP4s open through `load_video_frames()` / OpenCV and contain frames.
- [x] Re-running with `--skip-existing` does not overwrite existing takes.
- [x] Re-running with `--retry <phrase_id>` replaces the selected phrase's media and keeps `phrases.jsonl` stable.
- [x] Unit tests cover path generation, JSONL updates, validation, and dry-run collection.

## Out of scope

- Training or fine-tuning any model. This ticket creates eval data only.
- Automatically improving the live pipeline after data collection. TICKET-020 owns running and interpreting the evaluation.
- Building a GUI recorder. CLI plus clear prompts is enough for the PoC.
- Cloud upload or dataset sharing. Media remains local and should stay out of git.

## Notes

- This is "personal eval data", not "training data". The current pipeline does not learn from it automatically.
- Prefer relative paths in `phrases.jsonl` so the dataset folder can move as a unit.
- Keep raw media out of git. Update `.gitignore` if the new collection directory needs explicit media ignore rules.

## References

- TICKET-014 - eval harness that consumes `phrases.jsonl`.
- TICKET-017 - fused dictation pipeline being evaluated.
- TICKET-018 - cleanup prompt A/B can be layered into the same eval dataset.
