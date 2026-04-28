# TICKET-051 - Auto-update and release channels

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-049, TICKET-050
Status: Not started

## Goal

Wire `electron-updater` so installed users get automatic updates on Windows (NSIS) and macOS (DMG/zip), with `stable` and `beta` channels and basic staged rollout. Updates require signed builds (already enforced in TICKET-049 / TICKET-050); without signing, auto-update on macOS is impossible and on Windows is misleading.

## System dependencies

- A publish target: GitHub Releases for v1, generic S3/R2-compatible bucket as the production target later.
- Signed Windows + macOS artifacts produced by TICKET-049 + TICKET-050.

## Python packages

None.

## Work

- `desktop/build/electron-builder.yml`:
  - `publish` block for `github` (v1) with `provider`, `owner`, `repo`, `releaseType`.
  - `electronUpdaterCompatibility: ">= 2.16"`.
  - Channels: produce both `stable` and `beta` `latest*.yml` files.
- App integration (`desktop/electron/updater.ts`):
  - On boot and every 24 h, call `autoUpdater.checkForUpdatesAndNotify()`.
  - Surface "Update available" / "Downloading" / "Ready to install" notifications via the tray menu and a settings panel row.
  - "Restart and update" button drives `autoUpdater.quitAndInstall()`.
- Channel selection:
  - Settings entry "Update channel" (Stable / Beta), persisted in the settings store (TICKET-046).
  - Switching channel triggers an immediate update check.
- Staged rollout:
  - Use the percentage flag in the `latest*.yml` to roll out to a subset of users first.
  - Document the bump procedure in `docs/distribution_packaging/RELEASES.md`.
- Testing harness:
  - `dev-app-update.yml` for local update flow testing without a real release.
  - Document how to test against a Minio-backed bucket per electron-builder's recommendation.
- Telemetry (deferred): no install/update telemetry in v1, but leave hooks for future.

## Acceptance criteria

- [ ] Publishing a new tagged release with signed artifacts triggers update detection in the installed app within one launch cycle on Windows and macOS.
- [ ] "Update available" surfaces in the tray and settings; the user can defer or install now.
- [ ] Switching from `stable` to `beta` immediately offers the newer beta build.
- [ ] Staged rollout percentage in `latest.yml` is honored (verifiable via dev-app-update.yml).
- [ ] Auto-update on macOS works end-to-end on signed + notarized builds.
- [ ] `docs/distribution_packaging/RELEASES.md` documents the bump + rollout procedure.
- [ ] Unsigned local dev builds gracefully no-op the updater rather than crashing.

## Out of scope

- Cross-platform auto-update for Linux (TICKET-054).
- Diff-only / delta updates.
- Server-side rollout dashboards (we use static `latest*.yml` percentages).

## Notes

- macOS auto-update without signing is not "hard"; it is impossible. Treat TICKET-050 as a hard prerequisite.
- Squirrel.Windows is unsupported for simplified auto-update; stay on NSIS.
- Always bump `electronUpdaterCompatibility` deliberately - downgrading older clients silently is the worst possible bug.

## References

- `project_roadmap.md` lines 272-277 - auto-update plan.
- TICKET-049 / TICKET-050 - signed artifacts the updater consumes.
