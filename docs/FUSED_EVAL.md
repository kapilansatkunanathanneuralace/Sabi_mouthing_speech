# Personal Fused Eval

This is the repeatable loop for testing Sabi's fused dictation pipeline on your own
face, microphone, camera, and room. It measures the current pipeline. It does not
train or fine-tune a model.

## 1. Collect Data

First create a fused eval dataset with paired MP4/WAV files:

```powershell
python -m sabi collect-fused-eval `
  --camera-name "ACER FHD User Facing" `
  --mic-name "Microphone Array (Intel® Smart Sound Technology for Digital Microphones)"
```

For a short smoke run:

```powershell
python -m sabi collect-fused-eval `
  --limit 1 `
  --camera-name "ACER FHD User Facing" `
  --mic-name "Microphone Array (Intel® Smart Sound Technology for Digital Microphones)"
```

The expected layout is:

```text
data/eval/fused/
  phrases.jsonl
  video/
    harvard_001.mp4
  audio/
    harvard_001.wav
```

Each row in `phrases.jsonl` must have non-empty relative paths:

```json
{"id":"harvard_001","text":"The birch canoe slid on the smooth planks.","video_path":"video/harvard_001.mp4","audio_path":"audio/harvard_001.wav","tags":["harvard"]}
```

If you mess up and want to start collection over, preview the reset first:

```powershell
python -m sabi fused-eval-reset --dataset data/eval/fused
```

Then delete the generated `phrases.jsonl`, `video/*.mp4`, and `audio/*.wav`
files:

```powershell
python -m sabi fused-eval-reset --dataset data/eval/fused --yes
```

## 2. Validate The Dataset

Run the preflight check before the expensive model eval:

```powershell
python -m sabi fused-eval-check --dataset data/eval/fused
```

The check reports:

- phrase count
- valid phrase count
- missing video/audio files
- invalid video/audio files
- per-phrase errors with the field to fix

If it passes, it prints the exact eval command to run next.

## 3. Run Fused Eval

Run the personal fused baseline:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md
```

Eval probes and warms the Ollama cleanup model before measured rows by default.
If your report shows cleanup timeouts, give eval a larger cleanup budget:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --cleanup-timeout-ms 5000 --out reports/poc-eval-fused-personal.md
```

If you need to measure without the warm-up probe, disable it explicitly:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --no-cleanup-preflight --out reports/poc-eval-fused-personal.md
```

For a more stable number after the first smoke run, increase runs:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 3 --out reports/poc-eval-fused-personal.md
```

### Calibrated baseline (TICKET-036)

After TICKET-032 (confidence calibration) and TICKET-035 (cleanup timeout + preflight),
save a second report so fusion policy experiments have a clean before/after anchor.

Run the calibrated baseline (same dataset, longer cleanup budget):

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --cleanup-timeout-ms 10000 --out reports/poc-eval-fused-personal-calibrated.md
```

Generate tuning suggestions from the calibrated report:

```powershell
python -m sabi fused-tuning-suggest `
  --report reports/poc-eval-fused-personal-calibrated.md `
  --out reports/fused-tuning-suggestions-calibrated.md
```

Baseline comparison on the same 20-phrase fused dataset (see `reports/poc-eval-fused-personal.md`
vs `reports/poc-eval-fused-personal-calibrated.md`):

- **Cleanup health**: the older report timed out on cleanup for every row (`cleanup_fallback=yes`,
  `cleanup_reason=http_error: ReadTimeout`), so `raw_wer` and `cleaned_wer` matched because cleanup never ran.
  The calibrated rerun shows `cleanup_fallback_rate=0.00%`, so `cleaned_wer` now reflects real cleanup output.
- **Accuracy**: `raw_wer` stayed `0.316`, but `cleaned_wer` dropped from `0.316` to `0.237` once cleanup succeeded.
- **Confidence**: phrase-level `confidence` is no longer stuck at `1.00` on severe ASR/VSR disagreements; see the
  `Phrase Results` table in the calibrated report (for example `harvard_001` at `0.66` and `harvard_002` at `0.55`).
- **Latency**: wall-clock and per-stage medians can shift between runs depending on cold/warm model caches and
  background load. Always compare using the `## Summary` and `## Per-Stage Latency` tables from the specific report file.

### Fusion mode A/B (TICKET-037)

Use this **after** you have a calibrated baseline (TICKET-036). It runs the same fused eval once per
`FusionConfig.mode` and writes **one** markdown report so you can compare `auto`, `audio_primary`, and
`vsr_primary` on **measured** WER, confidence, latency, and high-confidence/high-WER counts.

```powershell
python -m sabi eval-fusion-modes `
  --dataset data/eval/fused `
  --modes auto,audio_primary,vsr_primary `
  --runs 1 `
  --cleanup-timeout-ms 10000 `
  --out reports/fusion-mode-ab-personal.md
```

The report includes:

- **Summary by mode**: mean `raw_wer` / `cleaned_wer`, cleanup fallback rate, `high_conf_high_wer` row counts, and
  end-to-end latency percentiles per mode.
- **Per-stage latency by mode**: quick view of whether one mode shifts ASR/VSR/ROI time (usually similar; large
  swings usually mean cache effects or a different failure mode).
- **Per-phrase cleaned WER by mode**: which mode wins per phrase on `cleaned_wer`, plus spread across modes.
- **Severe mode disagreements**: phrases where modes disagree strongly enough that changing defaults could matter.

Do **not** change the live fusion default based on a single run; use this report as evidence, then let TICKET-038
decide the policy change after you have a repeatable pattern on your dataset.

## 4. Optional Cleanup Prompt A/B

To compare cleanup prompts on the same fused dataset:

```powershell
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --cleanup-prompt v1,v2 --out reports/poc-eval-fused-personal-ab.md
```

Use this when you want to know whether prompt v2 helps your real fused transcripts
without changing the underlying ASR, VSR, or fusion behavior.

## 5. Read The Report

Open the report under `reports/`.

Key fields:

- `raw_wer`: how wrong the fused transcript was before cleanup.
- `cleaned_wer`: how wrong it was after cleanup.
- `cleanup_fallbacks`: how many measured rows fell back to raw text instead of cleaned text.
- `cleanup_fallback_rate`: the share of measured cleanup rows that fell back.
- `total_p50_ms`: normal end-to-end speed.
- `total_p95_ms`: slower tail cases that users still feel.
- `confidence`: fused confidence score for each phrase.
- `decision`: whether the pipeline would paste, dry-run, withhold, or error.
- `Fused Diagnostics`: why the fused phrase behaved the way it did.
- `Known Failure Modes`: phrases that had low confidence, cleanup fallback, missing face, silence, empty output, or other errors.

The `Fused Diagnostics` section shows the raw ASR and VSR branches side by
side:

- `asr_text` / `asr_confidence`: what the microphone branch heard and how confident it was.
- `vsr_text` / `vsr_confidence`: what the lip-reading branch saw and how confident it was.
- `fusion_mode` / `fusion_reason`: which fusion path won and why.
- `source_weights`: how much of the final phrase came from ASR vs VSR.
- `per_word_origin`: the source chosen for each word (`asr`, `vsr`, or `both`).
- `face_ratio`: how often the mouth/face was visible during the clip.
- `vad_coverage`: how much of the audio looked speech-like.
- `peak_dbfs`: loudest audio level; very low values usually mean the mic was too quiet.
- `cleanup_prompt`, `cleanup_fallback`, `cleanup_reason`: whether Ollama cleanup ran or fell back to raw text.
- `flags`: compact warnings like `high_conf_high_wer`, `asr_vsr_disagree`, `cleanup_fallback`, `low_face_ratio`, `low_vad_coverage`, or `low_audio_peak`.

Fused `confidence` is calibrated. It is lower when ASR and VSR disagree, when
alignment is weak, or when only one modality produced text. A remaining
`high_conf_high_wer` flag means the system was still very confident despite a
bad transcript, usually because both modalities agreed on the wrong phrase.

## 6. What The Results Mean

This dataset does not automatically change the live pipeline. There is no extra
"apply training" command in the current PoC.

Use the report to decide what to tune manually:

- If ASR is good and VSR is weak, improve camera framing, lighting, lip ROI, or VSR configuration.
- If VSR is good and ASR is weak, improve microphone input, room noise, or ASR settings.
- If both raw inputs are reasonable but fused text is worse, tune fusion thresholds or source weights.
- If raw WER is good but cleaned WER is worse, tune the cleanup prompt or compare `v1,v2`.
- If cleanup fallback rate is high, fix Ollama availability or increase `--cleanup-timeout-ms` before judging cleanup quality.
- If cleanup fallback rate is low but cleaned WER is worse than raw WER, cleanup ran and made the text worse; compare prompts or revise cleanup behavior.
- If latency is high, inspect the per-stage latency table to find the slow stage.
- If `high_conf_high_wer` appears, do not trust fused confidence yet; use it as input to confidence calibration.
- If `asr_vsr_disagree` appears often, compare the ASR/VSR text columns before changing the cleanup prompt.
- If `cleanup_fallback` appears, Ollama cleanup was bypassed or failed, so the report is measuring raw fusion output.

## 7. Get Tuning Suggestions

After you have a TICKET-030 report with `Fused Diagnostics`, ask the repo for a
manual tuning summary:

```powershell
python -m sabi fused-tuning-suggest --report reports/poc-eval-fused-personal.md
```

To save the suggestions:

```powershell
python -m sabi fused-tuning-suggest `
  --report reports/poc-eval-fused-personal.md `
  --out reports/fused-tuning-suggestions.md
```

This command does not edit config files, train models, or apply changes. It reads
the report and groups evidence into likely next actions:

- `Capture / VSR`: camera framing, lighting, lip ROI, or VSR settings look suspicious.
- `Microphone / ASR`: mic input, room noise, or ASR settings look suspicious.
- `Fusion Config`: ASR/VSR disagreement or hard source choices suggest fusion thresholds need testing.
- `Confidence Calibration`: high-confidence/high-WER phrases mean confidence is too optimistic.
- `Cleanup / Ollama`: cleanup fallback or timeout means the report is mostly raw fusion output.
- `Latency`: per-stage runtime should be inspected before accuracy tuning.
- `Model Fine-Tuning Candidate`: use as evidence for the research spike, not as proof to train.

## Quick Loop

```powershell
python -m sabi collect-fused-eval --limit 1 --camera-name "ACER FHD User Facing" --mic-name "Microphone Array (Intel® Smart Sound Technology for Digital Microphones)"
python -m sabi fused-eval-check --dataset data/eval/fused
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md
python -m sabi fused-tuning-suggest --report reports/poc-eval-fused-personal.md
```
