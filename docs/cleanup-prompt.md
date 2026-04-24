# Cleanup prompt versioning (TICKET-008)

The LLM cleanup pass lives in [`src/sabi/cleanup/ollama.py`](../src/sabi/cleanup/ollama.py)
and reads its system prompt from
[`src/sabi/cleanup/prompts/default.txt`](../src/sabi/cleanup/prompts/default.txt).
Prompts are plain text files so they are easy to diff, review, and A/B
without re-releasing the package.

## Versioning convention

- `prompts/default.txt` is always the **current production prompt**. It
  is the only file `TextCleaner` looks up by default.
- Before shipping a change, copy the current file to a dated variant so
  the baseline is still runnable:

    ```powershell
    Copy-Item src/sabi/cleanup/prompts/default.txt `
              src/sabi/cleanup/prompts/v1_2026-04-24.txt
    ```

- Keep the filename prefix `vN_YYYY-MM-DD.txt` (e.g. `v2_2026-05-01.txt`).
  The prefix makes diffs and eval spreadsheets easy to sort; the date
  disambiguates hot-fixes within the same minor version.
- Commit the dated baseline in the same change that bumps
  `default.txt`, so `git blame` on `default.txt` points at the PR that
  introduced the new version.

## A/B testing against the eval set

TICKET-014 will own a small fixture of raw-to-cleaned pairs under
`data/eval/`. Until then, A/B a prompt manually:

```powershell
# Run the baseline
Copy-Item src/sabi/cleanup/prompts/v1_2026-04-24.txt src/sabi/cleanup/prompts/default.txt
python -m sabi cleanup-smoke "um i i think we should like ship it"

# Swap in a candidate prompt and re-run
Copy-Item src/sabi/cleanup/prompts/candidate.txt src/sabi/cleanup/prompts/default.txt
python -m sabi cleanup-smoke "um i i think we should like ship it"
```

Compare the two outputs in `reports/latency-log.md` (same `stage=cleanup`
rows, different prompts) plus a visual read of the cleaned text.

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

When TICKET-014 arrives we will lock the prompt, capture its SHA into
the eval report, and treat prompt edits as versioned artifacts rather
than ad-hoc tweaks.
