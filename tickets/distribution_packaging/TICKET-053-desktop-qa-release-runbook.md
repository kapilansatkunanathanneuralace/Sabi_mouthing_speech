# TICKET-053 - Desktop app QA and release runbook

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-049, TICKET-050, TICKET-051, TICKET-052
Status: Not started

## Goal

Define the manual + scripted QA the desktop app must pass before each release, and write the operator runbook the on-call uses to actually cut a release. Output is a checklist that catches the install/upgrade/permission/model-download regressions that automated tests cannot.

## System dependencies

- Clean Windows 11 VM (or fresh user account).
- Clean macOS 13+ VM (or fresh user account).
- Optional: a "stale-cache" VM that already has an older version installed for upgrade testing.

## Python packages

None.

## Work

- `docs/distribution_packaging/RELEASE_RUNBOOK.md`:
  - Pre-release checklist (CI green, signing creds verified, ADR-001 still accurate, model manifests current).
  - Tag + publish steps.
  - Staged rollout instructions (5% -> 25% -> 100%).
  - Rollback playbook (re-publish previous artifacts, force `latest*.yml` revert).
- `docs/distribution_packaging/QA_CHECKLIST.md`:
  - Install on Windows: per-user, no admin, no SmartScreen warning on signed builds, app launches.
  - Install on macOS: drag-to-Applications, Gatekeeper accepts, app launches.
  - Onboarding flow: every step on each OS, including the "skip optional" path.
  - Permissions: deny each prompt at least once, ensure the app shows clear remediation.
  - Model download: success, network failure mid-way, hash mismatch, retry.
  - Dictation surfaces: silent, audio, fused - each `--dry-run` and live, with hotkey trigger from Electron only.
  - Upgrade: install old version, install new version, verify settings + cache survive.
  - Uninstall: clean removal on Windows, drag-to-trash on macOS, optional cache cleanup.
  - Auto-update: stable -> stable bump, stable -> beta switch, rollback path.
  - Tray + shortcut behavior with the app idle vs running.
  - Crash recovery: kill the sidecar from Activity Monitor / Task Manager, ensure the app reconnects.
- Known limitations + workarounds:
  - Large bundle size and first-launch download timing.
  - GPU/CUDA variance: Windows works on CUDA 12.1, CPU otherwise; macOS is CPU/MPS.
  - macOS Accessibility opacity.
  - `keyboard` library behaviors that no longer apply once Electron owns shortcuts.
- "Definition of release-ready":
  - All QA checklist items signed off.
  - Latest CI run on the release tag is green.
  - Signed artifacts exist for both platforms.
  - At least one full upgrade test from the previous release.

## Acceptance criteria

- [ ] `docs/distribution_packaging/RELEASE_RUNBOOK.md` exists with pre-release, release, rollout, and rollback sections.
- [ ] `docs/distribution_packaging/QA_CHECKLIST.md` exists and covers install, onboarding, permissions, model download, dictation, upgrade, uninstall, auto-update, and crash recovery on both Windows and macOS.
- [ ] The checklist is small enough to run in under one hour by one operator.
- [ ] Known limitations + their workarounds are documented in the checklist.
- [ ] At least one practice release is performed end-to-end against the runbook and feedback is folded back into the doc.

## Out of scope

- Automating any of the manual QA steps (separate ticket if the manual cost gets too high).
- Telemetry of QA outcomes.
- Public-facing release notes; this ticket is internal QA + release ops.

## Notes

- Manual QA is not a stand-in for missing automation; it catches the things automation cannot reach (real OS permission prompts, real Gatekeeper behavior).
- Treat the runbook as a living doc - every release adds at least one bullet.
- Keep the checklist close to the code; do not let it drift to a separate wiki.

## References

- TICKET-049 / TICKET-050 - artifacts under test.
- TICKET-051 - auto-update flows under test.
- `project_roadmap.md` line 307 - "Internal dogfood, capture install metrics".
