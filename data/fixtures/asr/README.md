# ASR smoke fixtures

`sabi asr-smoke` (TICKET-007) needs a short recorded clip plus a plain-text
ground truth transcript alongside it:

- `hello_world.wav` - ~2 s, **16 kHz mono PCM**, clearly saying "hello world".
- `hello_world.txt` - "hello world" (single line, already checked in).

The `.wav` is intentionally **not** committed: it is user-specific and would
bloat the repo. Produce one locally in any of these ways:

1. Record with the sabi mic stack (TICKET-006) and export the utterance to
   wav, or
2. Record with any OS tool (e.g. Windows Voice Recorder, Audacity), then
   re-encode with ffmpeg:

    ```powershell
    ffmpeg -i recording.m4a -ar 16000 -ac 1 -sample_fmt s16 `
      data/fixtures/asr/hello_world.wav
    ```

3. Synthesize one with a TTS tool of your choice; any English "hello world"
   at 16 kHz mono will do.

Once both files exist, run:

```powershell
python -m sabi asr-smoke data/fixtures/asr/hello_world.wav
```

Expected output:

- `text` roughly equal to `"hello world"` (case / punctuation may vary).
- `WER < 10%` against `hello_world.txt` (computed automatically when
  `jiwer` is installed).
- `latency < 500 ms` on CPU INT8, `< 200 ms` on CUDA.

The CLI prints a WARNING - it never hard-fails - if any threshold is
missed, matching the TICKET-007 acceptance wording ("logged rather than
hard-failed in test").
