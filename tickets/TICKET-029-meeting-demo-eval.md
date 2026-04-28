# TICKET-029 - Meeting demo runbook + listening-test eval

Phase: 1 - ML PoC
Epic: Eval
Estimate: M
Depends on: TICKET-015, TICKET-027, TICKET-028
Status: Not started

## Goal

Ship `docs/DEMO-MEETING.md` so a reviewer can reproduce silent meeting mode in Zoom/Teams/Meet, and extend eval support with a meeting-mode track that measures end-to-end latency and captures synthesized audio for human listening scores.

## System dependencies

- Everything from TICKET-015 plus VB-Cable and a real meeting client.
- Optional second account or second participant for demo verification.

## Python packages

Already listed for eval extras:

- `jiwer`, `pandas`, `tabulate`

New eval-only:

- `librosa` for loading captured WAVs and basic audio summaries.

## Work

- Write `docs/DEMO-MEETING.md` covering prerequisites, meeting-client config, live demo steps, mute drill, eval runbook, and failure modes.
- Extend `sabi.eval.harness` with a meeting track using a capturing sink.
- Write `reports/meeting-eval-<date>/scorecard.csv` for human MOS-style scoring.
- Add `scripts/meeting_live_latency.py` as a manual latency probe.
- Extend `tests/test_eval_harness.py` for meeting-track output.
- Cross-link meeting docs from `README.md`, `tickets/README.md`, and `docs/DEMO.md`.

## Acceptance criteria

- [ ] A developer can reproduce PoC-4 in a test meeting from the docs.
- [ ] `python -m sabi eval --pipelines silent_meeting --capture --dataset data/eval/sample` produces a markdown report, captured WAVs, and scorecard CSV.
- [ ] Scorecard CSV columns match the documented listening-test protocol.
- [ ] Captured WAVs are mono and decodable by `librosa.load`.
- [ ] `scripts/meeting_live_latency.py` writes a measurement file under `reports/`.
- [ ] Known failure modes are documented.
- [ ] README and ticket links resolve.
- [ ] `scripts/record_demo.ps1` supports a meeting recording mode.

## Out of scope

- Automated human scoring.
- PESQ / STOI implementation.
- Two-way Zoom network latency.
- Multi-language meeting eval.
- Sharing captured audio externally.

## Notes

- Capture from the in-process sink for pipeline latency; device loopback adds Windows audio jitter.
- Keep scorecards easy to fill in a spreadsheet.

## References

- Roadmap Flow 2 latency budget (project_roadmap.md lines 124-136).
- Roadmap Phase 1 Week 3 (project_roadmap.md line 176).
- Roadmap risks (project_roadmap.md lines 218-225).
