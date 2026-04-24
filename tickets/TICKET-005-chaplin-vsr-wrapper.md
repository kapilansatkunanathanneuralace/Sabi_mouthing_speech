# TICKET-005 - Chaplin / Auto-AVSR wrapper

Phase: 1 - ML PoC
Epic: VSR
Estimate: L
Depends on: TICKET-004
Status: Not started

## Goal

Wrap Chaplin (which is itself built on Auto-AVSR) behind a stable internal interface `VSRModel.predict(lip_frames) -> VSRResult(text, confidence, per_token_scores)` so the pipeline does not care which upstream checkpoint we are using this week. First-run downloads weights via a scripted fetch; inference runs on CUDA when available and falls back to CPU with a loud log line and a latency warning.

## System dependencies

- CUDA 12.1 + compatible NVIDIA driver for GPU inference (optional but strongly recommended - CPU inference on Chaplin is multi-second per utterance).
- `git` (to clone Chaplin as a submodule or vendored third-party).
- Disk space: approx 2 GB for weights + model cache.

## Python packages

Already available from TICKET-002:

- `torch`, `torchaudio`
- `numpy`
- `opencv-python`

New, Chaplin-specific (add to `pyproject.toml` dependencies):

- `sentencepiece==0.2.0` - tokenizer used by Auto-AVSR checkpoints.
- `omegaconf==2.3.0` - Chaplin reads hydra-style configs.
- `pytorch-lightning==2.3.3` - Chaplin's training framework; inference imports live inside it. Pinned to avoid Lightning 2.4 breakage.
- `av==12.3.0` - video I/O used by Chaplin's test scripts.
- `editdistance==0.8.1` - used by the model for its own confidence metrics on nbest.

If Chaplin is vendored as a git submodule (preferred) rather than pip-installed, list the above explicitly even though Chaplin's own `requirements.txt` pulls them. Our `pyproject.toml` remains the single source of truth.

## Work

- Decide and document vendoring strategy in `docs/MODELS.md`: preferred approach is git submodule at `third_party/chaplin/` with a pinned commit sha. If Chaplin exposes a pip package by implementation time, switch to pinning it in `pyproject.toml` instead.
- Create `src/sabi/models/vsr.py` with:
  - `VSRModelConfig`: checkpoint path, device preference (`"cuda" | "cpu" | "auto"`), precision (`"fp16" | "fp32"`), max input length (frames).
  - `VSRResult` dataclass: `text`, `confidence` (float 0-1), `per_token_scores` (list[float] or None), `latency_ms` (detector input -> text output).
  - `VSRModel` class with `__enter__`/`__exit__`, lazy weight load on first `predict`.
  - `.predict(lip_frames: Sequence[np.ndarray]) -> VSRResult`:
    - Asserts frames are 96x96 uint8 grayscale (matches TICKET-004 output contract).
    - Normalizes using Auto-AVSR mean/std constants, stacks to a `(1, T, 1, 96, 96)` tensor.
    - Runs model forward under `torch.inference_mode()` with the configured precision.
    - Decodes via the model's built-in CTC/attention beam search; surfaces average log-prob as confidence.
  - `.predict_streaming(iter_of_frames)` - convenience wrapper that batches frames on utterance boundaries provided by the caller (TICKET-011).
- Write `scripts/download_vsr_weights.py`:
  - Pulls the Chaplin release checkpoint (URL + sha256 recorded in `configs/vsr_weights.toml`).
  - Verifies the hash. Refuses to overwrite unless `--force`.
  - Stores under `data/models/vsr/` (git-ignored).
- Wire CLI: `python -m sabi download-vsr` calls the script; `python -m sabi vsr-smoke <video_path>` runs the model on a saved sample and prints the result + latency.
- Add a regression fixture: a short silent speech clip under `data/fixtures/vsr/hello_world.mp4` plus its ground-truth transcript in a sibling `.txt`. The smoke test runs end-to-end on that file.

## Acceptance criteria

- [ ] `python -m sabi download-vsr` on a clean clone fetches and hash-verifies the weights, refuses to re-download without `--force`, and exits 0.
- [ ] `python -m sabi vsr-smoke data/fixtures/vsr/hello_world.mp4` produces a transcript string matching the ground truth to within 30% WER on the reference GPU laptop (looser threshold is acceptable given Chaplin's noted in-the-wild weakness from the roadmap risks section).
- [ ] Same smoke command on a CPU-only machine exits 0 but logs a WARNING that latency will exceed the 200 ms budget; per-sample latency is captured in `reports/latency-log.md`.
- [ ] `VSRModel.predict` raises `VSRInputError` on frames that are not 96x96 uint8 grayscale.
- [ ] `tests/test_vsr_wrapper.py` uses a mocked model to verify: config plumbing, FP16/FP32 branch, precision-of-latency timing, and `VSRResult` shape.

## Out of scope

- Fine-tuning Chaplin on user data - Phase 2 roadmap item (project_roadmap.md line 219).
- Swapping to VALLR or a custom in-house model - explicit "upgrade path" in the roadmap core models table.
- Streaming partial hypotheses - we decode one utterance at a time. Streaming hypotheses are a TICKET-013 "nice to have" if time allows.
- Audio-visual fusion - that is TICKET-011 or later, not here.

## Notes

- Chaplin is described in the roadmap as a **validator**, not a production model, so aim for robustness of the wrapper rather than fighting accuracy. Anything we learn here informs the Phase 2 fine-tune plan.
- Keep the normalization and frame-rate assumptions in a single constants module (`sabi.models.vsr.constants`) so TICKET-004 and TICKET-011 share one source of truth.

## References

- Roadmap core models table (project_roadmap.md line 25) - "VSR (lip reading): Chaplin / Auto-AVSR" is this ticket.
- Roadmap Flow 1 step 4 (project_roadmap.md line 85) - "VSR model predicts text from lip motion: 100-200 ms" is the latency budget we measure against.
- Roadmap risks (project_roadmap.md line 219) - "Chaplin is a validator, not a production model" informs acceptance thresholds.
- Chaplin repo: https://github.com/amanvirparhar/chaplin (or successor) - pinned sha lives in `configs/vsr_weights.toml`.
