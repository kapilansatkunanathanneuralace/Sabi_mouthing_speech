# Personal VSR Fine-Tuning Research

This is the TICKET-033 research result for whether Sabi can fine-tune the
Chaplin / Auto-AVSR visual speech model on one person's collected fused eval
data.

## Recommendation

Do not implement true personal VSR fine-tuning in this repo yet.

Recommended next step: collect more held-out personal data and keep improving
fusion, confidence calibration, capture quality, and cleanup first. The current
repo has a solid inference wrapper, but it does not include an Auto-AVSR training
entrypoint, training dataset manifests, optimizer/scheduler config, checkpoint
resume flow, or an adapter/LoRA path.

TICKET-034 should be deferred or rewritten unless a future ticket first selects
an actual upstream training recipe. Exporting today's `data/eval/fused` as a
"training" set would risk overfitting and eval leakage.

## Evidence From This Repo

Chaplin is vendored under `third_party/chaplin`. The checked-in path is built
for inference:

- `third_party/chaplin/main.py` starts the webcam and loads `InferencePipeline`.
- `third_party/chaplin/pipelines/pipeline.py` loads media, landmarks, and calls
  `AVSR.infer`.
- `third_party/chaplin/pipelines/model.py` constructs the ESPnet model, loads a
  pretrained checkpoint, builds beam search, and calls `model.encode`.
- `third_party/chaplin/configs/LRS3_V_WER19.1.ini` points to pretrained model
  and language model weights.
- `src/sabi/models/vsr/model.py` wraps the same inference path and rewrites the
  config to absolute pretrained weight paths.

No runnable training script was found in the vendored Chaplin tree. There are
ESPnet utility functions with training-related helpers, but the repo does not
ship the top-level Auto-AVSR training pipeline needed to fine-tune safely.

The personal fused eval report also does not prove VSR fine-tuning is the next
best move. `reports/fused-tuning-suggestions.md` shows:

- 20 rows with ASR/VSR disagreement.
- 6 severe WER rows.
- Cleanup fallback on all rows due to Ollama timeout.
- Several severe failures caused by `alignment_below_threshold` and hard source
  choices.

That is useful evidence, but it points first to confidence, fusion, cleanup, and
capture work. It is not enough to claim a VSR model update would help.

## Expected Training Data Shape

If a future ticket adopts upstream Auto-AVSR training, the personal export will
likely need more than the current eval JSONL:

- Video clips at 25 FPS or resampled to match the model's video FPS.
- Mouth/lip crops matching the current inference contract: 96x96 grayscale
  crops before Chaplin's `VideoTransform`.
- The same normalization path used by Chaplin: scale to `[0, 1]`, center-crop
  to 88, then normalize with LRS3 mean/std.
- Text transcripts aligned to each clip.
- Tokenization compatible with the model config. The current model uses a
  subword/token list path such as `pipelines/tokens/unigram5000_units.txt` when
  configured for `unigram5000`.
- A train/validation split with no phrase overlap.
- A held-out eval set that is not used for training, tuning, or early stopping.
- Metadata that preserves speaker, phrase id, capture device, duration, and
  tags, so failures can be traced later.

The current `data/eval/fused/phrases.jsonl` has the right starting idea:
`id`, `text`, `video_path`, `audio_path`, and `tags`. It is eval metadata, not a
complete training manifest.

## Dataset Size Estimate

The current personal set is about 20 Harvard phrases. That is not enough for
true VSR fine-tuning.

Practical guidance:

- 20 phrases: useful for smoke eval only.
- 100-300 phrases: useful for a better personal validation set and config
  tuning, still risky for model training.
- 500-1,000+ utterances across different lighting, speaking rates, and days:
  a more plausible minimum before considering personal adaptation.

Even then, keep a held-out split. Do not train and evaluate on the same
phrases.

## Hardware And Runtime

Full Auto-AVSR fine-tuning is GPU work. Without the upstream training recipe in
this repo, exact numbers would be speculative, but realistic expectations are:

- CPU: not practical.
- 8 GB GPU: may be too tight for full transformer fine-tuning.
- 12-24 GB GPU: more realistic for experiments, depending on batch size,
  precision, and whether the full model or only part of it is updated.
- Runtime: hours to days for real fine-tuning; minutes only for a toy dry-run.

Adapter/LoRA or last-layer-only tuning would be preferable for personal data,
but this vendored Chaplin code does not expose an adapter or LoRA path.

## Tiny Dry-Run Outcome

No training dry-run was executed.

Reason: the vendored Chaplin tree does not contain a top-level training command
or a documented personal-data training format. Running a fake training command
would only prove that a script can start, not that personal fine-tuning is valid
or safe.

## Risks

- Overfitting: a small personal phrase set can memorize text instead of learning
  robust lip motion.
- Evaluation leakage: using `data/eval/fused` for both training and reporting
  would make WER look better without real generalization.
- Catastrophic forgetting: updating the full model on one speaker could damage
  general performance.
- Vocabulary/tokenizer mismatch: changing transcripts without matching the
  original tokenization path can produce invalid training targets.
- GPU limits: full model fine-tuning may not fit on common laptop GPUs.
- Privacy: exported training media contains the user's face and voice.

## Decision

Current decision: collect more data first, tune fusion/configuration first, and
defer true VSR fine-tuning.

Suggested follow-up:

- Keep TICKET-034 deferred until an upstream Auto-AVSR training recipe is chosen.
- If revisiting training, create a new implementation ticket that first vendors
  or documents the upstream training script, expected manifest format,
  checkpoint resume behavior, and held-out evaluation protocol.
- Continue using `fused-tuning-suggest` and `Fused Diagnostics` to decide whether
  VSR is actually the bottleneck before spending time on training.
