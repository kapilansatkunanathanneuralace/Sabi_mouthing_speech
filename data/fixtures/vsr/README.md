# VSR smoke fixtures

`sabi vsr-smoke` (TICKET-005) needs a short recorded clip plus a plain-text
ground truth transcript alongside it:

- `hello_world.mp4` - 2-3 s, 25 fps, face clearly visible, saying "hello world".
- `hello_world.txt` - "hello world" (single line, already checked in).

The `.mp4` is intentionally **not** committed: it is user-specific and would
bloat the repo. Record one with any webcam and save it as
`data/fixtures/vsr/hello_world.mp4`, or generate one via
`scripts/gen_vsr_fixture.py` if/when that helper lands (not part of this
ticket). Once both files are in place, run:

```sh
python -m sabi download-vsr
python -m sabi vsr-smoke data/fixtures/vsr/hello_world.mp4
```
