# Audio-Visual Fusion Module

`sabi.fusion` is the pure-Python combiner for TICKET-016. It takes one `ASRResult` and one `VSRResult`, aligns their words, chooses the best word at each position, and returns a `FusedResult`. It does not open the camera, microphone, models, Ollama, clipboard, or hotkeys.

## Public API

```python
from sabi.fusion import FusionCombiner, FusionConfig

combiner = FusionCombiner(FusionConfig(mode="auto"))
result = combiner.combine(asr_result, vsr_result)
```

The module also exposes a test-friendly function:

```python
from sabi.fusion import combine

result = combine(asr_result, vsr_result)
```

## FusionConfig

Defaults live in `configs/fusion.toml`.

| Field | Default | Meaning |
| --- | --- | --- |
| `mode` | `"auto"` | `"auto"`, `"audio_primary"`, or `"vsr_primary"`. |
| `asr_confidence_floor` | `0.4` | ASR confidence floor, matching audio dictation. |
| `vsr_confidence_floor` | `0.35` | VSR confidence floor, matching silent dictation. |
| `auto_switch_low_conf_ratio` | `0.5` | In auto mode, switch toward VSR if too many ASR words are below floor. |
| `tie_epsilon` | `0.02` | Treat smaller confidence deltas as ties. |
| `tie_breaker` | `"asr"` | Source used for true confidence ties. |
| `min_alignment_ratio` | `0.5` | If transcripts barely align, return one source verbatim instead of stitching. |

## Mode Resolution

Explicit modes are honored:

- `audio_primary`: ASR owns ties and insert/delete decisions.
- `vsr_primary`: VSR owns ties and insert/delete decisions.

In `auto`, the combiner starts as `audio_primary` because ASR is currently the stronger baseline. It switches to `vsr_primary` when:

- ASR overall confidence is below `asr_confidence_floor` and VSR clears `vsr_confidence_floor`.
- More than `auto_switch_low_conf_ratio` of ASR word confidences are below the ASR floor.

If one source is empty, mode resolution is skipped:

- Empty ASR returns VSR with `mode_used="vsr_primary"` and `mode_reason="asr empty"`.
- Empty VSR returns ASR with `mode_used="audio_primary"` and `mode_reason="vsr empty"`.
- Both empty returns empty text with `confidence=0.0`.

## FusedResult Schema

| Field | Meaning |
| --- | --- |
| `text` | Final fused transcript. |
| `confidence` | Calibrated fused confidence, clamped to `[0, 1]`. |
| `source_weights` | Share of emitted words from ASR and VSR. `both` counts half toward each. |
| `per_word_origin` | One entry per output word: `"asr"`, `"vsr"`, or `"both"`. |
| `per_word_confidence` | Confidence used for each output word. |
| `mode_used` | Resolved mode used for the output. |
| `mode_reason` | Short explanation of the mode choice. |
| `latency_ms` | Wall-clock time spent inside the combiner. |

## Alignment Rules

The combiner tokenizes on whitespace, normalizes tokens to lowercase for alignment, and preserves original surface tokens for output. It uses a small in-tree Needleman-Wunsch aligner with match `+1`, mismatch `-1`, and gap `-1`.

When aligned words match case-insensitively, origin is `both` and the output uses the primary source surface form. When they disagree, the higher per-word confidence wins. If confidence is tied within `tie_epsilon`, the primary source or `tie_breaker` wins. Unaligned insertions are kept only from the primary source.

If the matched alignment ratio is below `min_alignment_ratio`, the combiner returns the higher-confidence source verbatim. This avoids unstable mixed sentences when ASR and VSR disagree wildly.

## Confidence Calibration

`FusedResult.confidence` is intentionally more conservative than the raw model
confidence. The live fused pipeline uses this value for paste gating, so it
should be honest about disagreement.

Rules:

- Full ASR/VSR agreement keeps the emitted word confidence.
- Partial disagreement lowers confidence based on how many output words came from `both`.
- Low alignment lowers confidence further before returning one source verbatim.
- Missing ASR or missing VSR is capped at `0.85`, even if the surviving model reports `1.0`.
- A `1.00` fused confidence should only happen when both modalities agree and the underlying confidences support it.

The original per-word model scores are still exposed as `per_word_confidence`;
the final `confidence` is the calibrated score used by downstream decisions.

## Worked Example

```powershell
python -m sabi fusion-smoke --asr-text "ship by friday" --vsr-text "ship by friday" --asr-conf 0.9 --vsr-conf 0.5
```

Expected shape:

```json
{
  "text": "ship by friday",
  "source_weights": {
    "asr": 0.5,
    "vsr": 0.5
  },
  "per_word_origin": ["both", "both", "both"],
  "mode_used": "audio_primary"
}
```

Because both transcripts agree on every word, each word origin is `both`. ASR is still the primary source in auto mode because it clears the ASR confidence floor.

## JSON Smoke Inputs

`fusion-smoke` can also read two JSON files matching the result dataclasses:

```powershell
python -m sabi fusion-smoke asr-result.json vsr-result.json
```

Use the text shortcuts for quick debugging and JSON files when inspecting saved model outputs.
