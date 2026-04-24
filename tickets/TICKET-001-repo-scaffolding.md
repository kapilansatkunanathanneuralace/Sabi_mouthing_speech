# TICKET-001 - Repo scaffolding & Python env

Phase: 1 - ML PoC
Epic: Infra
Estimate: S
Depends on: -
Status: Not started

## Goal

Stand up the Python project skeleton so every other ticket has a predictable place to drop code, configs, data, and tests. After this ticket, `python -m sabi --help` runs (even if it prints nothing useful yet) and linting/formatting are wired. No ML dependencies installed yet - those come in TICKET-002.

## System dependencies

- Python 3.11 (64-bit). Pin with a `.python-version` file so downstream tickets do not drift.
- Git (already present).
- Windows 10/11 shell (PowerShell) is the reference environment; no WSL required.

## Python packages

Only the packaging and tooling baseline - no ML libs yet:

- `pip` >= 24.0
- Dev-only: `ruff`, `black`, `pytest`.

These go into `pyproject.toml` under `[project.optional-dependencies].dev`.

## Work

- Create the directory layout:

  ```
  src/sabi/
    __init__.py
    __main__.py          # thin CLI entry: `python -m sabi ...`
    cli.py               # argparse/typer stub (Typer added in TICKET-002 if we choose it)
  scripts/               # one-off developer scripts (probes, downloads)
  configs/               # YAML/TOML runtime configs
  data/
    eval/                # reserved for TICKET-014 phrase set
  tests/
  reports/               # latency-log.md lives here
  docs/
  ```

- Write `pyproject.toml` with:
  - `[project]` name `sabi`, version `0.0.0`, Python >= 3.11.
  - `[project.scripts] sabi = "sabi.cli:main"`.
  - `[tool.ruff]` with line length 100, target-version `py311`.
  - `[tool.black]` line length 100.
  - `[tool.pytest.ini_options]` rootdir + `testpaths = ["tests"]`.
- Write `.gitignore` (Python standard: `__pycache__/`, `.venv/`, `*.egg-info/`, `build/`, `dist/`, `.pytest_cache/`, `.ruff_cache/`, plus `data/eval/*.wav`, `data/eval/*.mp4`, `reports/*.md` except `reports/latency-log.md`).
- Write `.python-version` with `3.11`.
- Create `reports/latency-log.md` with a header row so every pipeline ticket has a file to append to.
- Add a one-paragraph `README.md` section describing the PoC and linking to `tickets/README.md` and `project_roadmap.md`. Keep existing top-level README text if present.
- Stub `src/sabi/cli.py` with a `main()` that prints `"sabi PoC - see tickets/README.md"` and exits 0.

## Acceptance criteria

- [ ] `python -m venv .venv` then `.\.venv\Scripts\pip install -e .[dev]` succeeds.
- [ ] `python -m sabi` prints the stub message and exits 0.
- [ ] `ruff check .` and `black --check .` both pass on the empty project.
- [ ] `pytest` runs (zero tests is fine) and exits 0.
- [ ] Directory layout above exists and is committed (empty dirs get a `.gitkeep`).
- [ ] `reports/latency-log.md` exists with a header row: `| ticket | hardware | stage | p50_ms | p95_ms | samples | notes |`.

## Out of scope

- Any ML libraries (opencv, mediapipe, torch, faster-whisper) - TICKET-002.
- Any actual CLI subcommands beyond the stub - pipelines get their CLI in TICKET-011 / TICKET-012.
- Dockerfile, CI config, pre-commit hooks - not needed for a single-dev PoC yet.

## References

- Roadmap TL;DR (project_roadmap.md lines 1-10) - establishes the audio-first, vision-validator framing this scaffolding serves.
- Roadmap Phase 1 (project_roadmap.md lines 170-177) - Week 1 milestone "Chaplin installed, faster-whisper wired up, text injection working" requires this scaffold to land first.
