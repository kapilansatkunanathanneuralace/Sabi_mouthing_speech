# Models

## VSR: Chaplin / Auto-AVSR (TICKET-005)

Chaplin is vendored as a git submodule at
[`third_party/chaplin`](../third_party/chaplin) pinned to the sha in
[`configs/vsr_weights.toml`](../configs/vsr_weights.toml). It ships its own
trimmed copy of `espnet` (under `third_party/chaplin/espnet/`), so we do not
need to pip-install the full espnet package.

### Initial setup

```sh
git submodule update --init --recursive
python -m sabi download-vsr
```

`download-vsr` reads the manifest in `configs/vsr_weights.toml`, downloads each
file into `data/models/vsr/<relative_path>` (git-ignored), and verifies sha256
when a non-empty hash is present. Re-downloading over an existing file requires
`--force`.

The committed manifest pins known-good `sha256` values for each file; a
download fails if any digest does not match. If Hugging Face artifacts change,
run `python -m sabi download-vsr --print-hashes` (or the same flag on
`scripts/download_vsr_weights.py`), update `configs/vsr_weights.toml`, and
commit.

### How `VSRModel` resolves paths

`VSRModel` reads the Chaplin ini (default
`third_party/chaplin/configs/LRS3_V_WER19.1.ini`), rewrites each relative
model/LM path to the downloaded absolute path under `data/models/vsr/...`,
and writes the result to a temp ini that Chaplin's `ConfigParser` then loads.
That way nothing cares about the current working directory at inference time.

### CUDA vs CPU

Chaplin inference is multi-second per utterance on CPU. When
`torch.cuda.is_available()` is `False`, `VSRModel` and `sabi vsr-smoke` log a
loud warning that the 200 ms roadmap budget is not achievable and fall back to
CPU anyway (no hard failure, because TICKET-011 pipeline tests want it to
still run). Expect the 30% WER acceptance target only on the reference GPU
laptop.

### Upgrading the Chaplin pin

1. `cd third_party/chaplin && git fetch && git checkout <new-sha>`
2. Update `sha` in [`configs/vsr_weights.toml`](../configs/vsr_weights.toml).
3. Re-run `python -m sabi download-vsr --force` if weights moved.
4. Re-run `tests/test_vsr_wrapper.py` plus the `vsr-smoke` fixture.

### Validator, not a production model

Per the [roadmap risks](../project_roadmap.md) section, Chaplin is explicitly
treated as a validator of the end-to-end pipeline; tight accuracy is not the
goal of this ticket. Phase 2 considers fine-tuning or swapping to VALLR.
