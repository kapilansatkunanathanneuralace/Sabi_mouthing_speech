# TICKET-060 - Onboarding state and launch polish

Phase: 4 - User Interface Flow
Epic: UX
Estimate: M
Depends on: TICKET-055, TICKET-056, TICKET-057, TICKET-058, TICKET-059
Status: Done

## Goal

Finalize the new phase-based onboarding flow by migrating persisted state,
polishing progress UI, updating tests and docs, and launching users into the
main desktop app after successful calibration.

## System dependencies

- Completed account, profile, permissions, device, shortcut, and calibration
  steps from TICKET-055 through TICKET-059.

## Python packages

None.

## Work

- Replace or migrate the old linear onboarding step model:
  - `welcome`.
  - `camera`.
  - `microphone`.
  - `accessibility`.
  - `models`.
  - `optional`.
  - `done`.
- Introduce a phase-based state model that can represent:
  - Account/auth.
  - Profile intake.
  - Permissions.
  - Device checks.
  - Shortcut setup.
  - Calibration.
  - Launch/done.
- Add migration logic for existing settings files so users already partway
  through or done with TICKET-047 onboarding do not get stuck on invalid steps.
- Preserve `onboardingCompleted` semantics for the dashboard gate, or replace it
  with a clearly documented equivalent.
- Update the wizard progress UI to show the three major phases and current
  substep without overwhelming users.
- Add a launch step after calibration that explains what happens next and opens
  the main Sabi app/dashboard.
- Ensure the main dashboard starts in a useful default state after onboarding:
  selected pipeline, shortcut, runtime status, and dictation history visible.
- Update docs in `desktop/README.md` and any distribution packaging docs that
  describe first launch.
- Add tests for:
  - Old settings migration.
  - Resume from each new phase.
  - Completed onboarding landing on the dashboard.
  - Progress indicator state.
  - Account panel hidden during onboarding and available after onboarding.

## Acceptance criteria

- [x] Existing settings with old onboarding steps migrate to valid new steps or
      completed state.
- [x] Users can quit and reopen during any new onboarding phase and resume
      without data loss.
- [x] The progress UI clearly shows Phase 1, Phase 2, Phase 3, and the current
      substep.
- [x] Completing calibration lands the user on a launch/finish step, then the
      main dashboard.
- [x] The dashboard does not show onboarding-only controls after completion.
- [x] Account status remains available after onboarding.
- [x] Desktop first-launch docs match the implemented phase-based flow.
- [x] Component tests cover migration, resume, progress, and launch behavior.

## Implemented

- Added migration-safe onboarding settings normalization for missing, completed,
  and invalid persisted step values.
- Added phase metadata helpers for Phase 1, Phase 2, Phase 3, and Launch.
- Replaced the internal step-pill progress row with phase progress and current
  substep copy.
- Polished the final `done` step into a launch step while preserving
  `onboardingCompleted` dashboard gating.
- Added a dashboard launch summary and updated first-launch docs.
- Added settings and renderer tests for migration, phase progress, resume, and
  launch behavior.

## Out of scope

- Adding new profile questions beyond TICKET-056.
- Changing permission semantics beyond TICKET-057.
- Changing calibration success thresholds beyond TICKET-059.
- Redesigning the entire dashboard after onboarding.

## References

- `desktop/electron/settings.ts` - persisted settings schema and migration
  boundary.
- `desktop/renderer/src/types/sidecar.ts` - renderer onboarding types.
- `desktop/renderer/src/onboarding/steps.ts` - current step ordering helper.
- `desktop/renderer/src/onboarding/OnboardingWizard.tsx` - wizard orchestration.
- `desktop/renderer/src/onboarding/__tests__/OnboardingWizard.test.tsx` -
  existing wizard tests.
- `desktop/README.md` - current first-launch onboarding docs.
