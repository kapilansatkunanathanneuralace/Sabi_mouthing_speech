# Cleanup prompt versioning (TICKET-018)

The LLM cleanup pass lives in [`src/sabi/cleanup/ollama.py`](../src/sabi/cleanup/ollama.py)
and resolves its system prompt through
[`src/sabi/cleanup/prompts/__init__.py`](../src/sabi/cleanup/prompts/__init__.py).
Prompts are plain text files so they are easy to diff, review, and A/B.

## Prompt versioning

`TextCleaner` selects prompts by `(prompt_version, register)`:

- `CleanupConfig.prompt_version = "v1"` is the default and preserves the
  original TICKET-008 behavior.
- `CleanupContext.register_hint = "dictation"` selects the dictation register.
- The resolver table maps `("v1", "dictation")` to
  [`v1_dictation.txt`](../src/sabi/cleanup/prompts/v1_dictation.txt) and
  `("v2", "dictation")` to
  [`v2_dictation.txt`](../src/sabi/cleanup/prompts/v2_dictation.txt).

To add a new version, add one prompt file and one resolver entry:

```python
("v3", "dictation"): PROMPT_DIR / "v3_dictation.txt"
```

The meeting register is intentionally not defined here; TICKET-022 owns
meeting cleanup.

## A/B testing against the eval set

Use the eval harness to compare v1 and v2 on the same dataset:

```powershell
python -m sabi eval --cleanup-prompt v1,v2 --dataset data/eval/sample --runs 1
```

The report includes `cleaned_wer_v1`, `cleaned_wer_v2`, and
`wer_delta_v2_minus_v1` columns. A negative delta means v2 improved WER.
The promotion bar for flipping the default is: aggregate
`wer_delta_v2_minus_v1 < 0` with at most a `+20 ms` p50 cleanup-latency
penalty on the reference dataset.

For quick manual checks:

```powershell
python -m sabi cleanup-smoke --prompt-version v2 "um i i think we should like ship it"
```

## Design principles

Short prompts beat clever prompts for this PoC:

- **Latency.** Every token the model reads counts against the
  ~300-400 ms budget (see TICKET-008 Notes). Aim for well under 1 kB of
  system prompt.
- **Scope.** Only describe filler removal, punctuation, casing, and
  stutter collapse. Anything broader drags the model into rewriting,
  which the hallucination guard in
  [`TextCleaner._is_hallucinated`](../src/sabi/cleanup/ollama.py) will
  throw away anyway.
- **Determinism.** `CleanupConfig.temperature` defaults to `0.2`. Raise
  it only while iterating manually; ship with low temperature so eval
  numbers are stable.
- **Meaning preservation.** The prompt repeats "do not add content" /
  "return only the cleaned text" because 3 B instruct models routinely
  append greetings or explanations.

## v2 dictation prompt - design notes

`v2_dictation.txt` is still short and keeps the original non-goals:

- Remove a stronger filler list: `um`, `uh`, `er`, `ah`, `mm`, filler
  `like`, `you know`, `i mean`, `kind of`, `sort of`, `basically`, and
  filler `literally`.
- Collapse stutters such as `I I I think`, `and and and`, and `the the`.
- Collapse hesitation runs such as `uh i mean um` and preserve useful
  emphasis words like `really`, `very`, and adverbial `actually`.
- Do not paraphrase, expand, switch register, or add facts. The
  hallucination guard still discards outputs that grow too much.

No pipeline default flips to v2 in TICKET-018. The default changes only
after the A/B report clears the promotion bar above.
