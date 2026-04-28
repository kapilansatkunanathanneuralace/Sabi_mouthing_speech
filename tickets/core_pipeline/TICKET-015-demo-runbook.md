# TICKET-015 - Demo runbook

Phase: 1 - ML PoC
Epic: Eval
Estimate: S
Depends on: TICKET-014
Status: Done

## Goal

Write `docs/DEMO.md` - the single document a new developer or a reviewer reads to reproduce **PoC-1 (silent dictation)** and **PoC-2 (audio dictation)** cold on a fresh Windows machine in under 60 minutes. Doubles as the "full internal demo" artifact the roadmap Phase 1 Week 2 milestone calls for. Also captures the observed "known failure modes" so Phase 2 planning starts with real data, not guesses.

## System dependencies

- A machine that passes `python -m sabi probe`.
- Camera + mic available to the user; Ollama optional but recommended.

## Python packages

None - this is a documentation ticket.

## Work

- Create `docs/DEMO.md` with the following sections:

  1. **Overview.** One paragraph linking to `project_roadmap.md` Flow 1, with a diagram-less summary of what the demo shows.
  2. **Prerequisites checklist.** Windows 10/11, Python 3.11, optional NVIDIA GPU, webcam, mic, Ollama, `git`, `ffmpeg`. Links to `docs/INSTALL.md`.
  3. **Cold-start steps.** Copy-paste PowerShell block that:
     - Clones the repo.
     - Creates `.venv`.
     - Installs torch with the CUDA 12.1 index line.
     - Installs the project with `pip install -e .[dev,eval]`.
     - Runs `python -m sabi probe` and explains how to read the output (expect "all green"; CUDA yellow is acceptable).
     - Downloads VSR weights via `python -m sabi download-vsr`.
     - Starts Ollama and pulls the cleanup model (exact `ollama pull ...` line from `configs/cleanup.toml`).
  4. **PoC-1 runbook (silent dictation).** Step-by-step: focus a Notepad window, `python -m sabi silent-dictate --ui tui`, hold the hotkey, mouth a phrase from `data/eval/phrases.sample.jsonl`, release, expect text in Notepad within ~500 ms. Screenshot placeholders and a "what should the TUI show" block.
  5. **PoC-2 runbook (audio dictation).** Same shape as PoC-1 but using `python -m sabi dictate`.
  6. **Eval runbook.** How to populate `data/eval/` with personal recordings, how to run `python -m sabi eval`, where the report lands, how to interpret the summary table.
  7. **Known failure modes.** A living list populated during dogfood. Seed entries the harness is expected to flag:
     - Low light -> MediaPipe loses the face -> silent pipeline aborts with no-face message.
     - Strong accent or fast speech -> faster-whisper stays accurate, Chaplin diverges.
     - Ollama unreachable -> both pipelines still work but cleanup rows show `bypassed`.
     - Target app debounces Ctrl+V (certain Slack builds) -> occasional missed paste despite log showing success.
     - Windows clipboard manager hooking the clipboard -> `restore_delay_ms` not enough, previous clipboard lost.
  8. **Known limitations.** Explicit "PoC is Windows-only, push-to-talk only, no fusion, no meeting mode, no packaging, single user, English only."
  9. **Next steps.** Bullet list pointing at the roadmap Phase 2 items (fusion, LLM cleanup polish, mode switcher, edge-case hardening) with a one-line justification per bullet rooted in the failure modes section.
- Add a shell script `scripts/record_demo.ps1` that starts an ffmpeg screen recording + webcam side-by-side for posterity so the Week 2 demo artifact can be captured cleanly.
- Cross-link from `tickets/README.md` and top-level `README.md` to `docs/DEMO.md`.
- Add `docs/DEMO.md` to `.gitattributes` as `linguist-documentation=true` so it does not skew language stats if we ever publish the repo.

## Acceptance criteria

- [x] A developer who has never seen the repo before can follow `docs/DEMO.md` and reach a successful silent-dictation paste in under 60 minutes on a prepared Windows laptop (time includes dependency installs and model downloads).
- [x] All commands in the cold-start block are copy-paste-correct PowerShell - verified by the author running them from scratch in a fresh user profile or VM.
- [x] `scripts/record_demo.ps1` produces a single `reports/demo-<date>.mp4` combining screen + webcam at 1080p30.
- [x] The "Known failure modes" section is populated with at least five entries, each naming the observed behavior and the log/report line where it shows up.
- [x] Links from `tickets/README.md` and `README.md` resolve.

## Out of scope

- Publishing a demo video externally - the artifact lives in `reports/` for now and is not committed.
- Packaged installer / end-user-facing docs - that is the Electron track, deferred out of PoC.
- Mac / Linux instructions - Windows-only. A follow-up ticket covers parity if we ever ship there.
- Long-form write-up about the model choices - that lives in `project_roadmap.md`; this doc is operational.

## References

- Roadmap Phase 1 Week 2 (project_roadmap.md line 175) - "Dictation + silent speech both functional. Full internal demo." is the milestone this runbook lets us declare done.
- Roadmap risks (project_roadmap.md lines 218-225) - the failure modes section is the cheapest place to accumulate real evidence for every listed risk.
