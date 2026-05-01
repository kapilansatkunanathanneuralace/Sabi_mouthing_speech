# TICKET-057 - Permissions branching and retry UX

Phase: 4 - User Interface Flow
Epic: UX
Estimate: M
Depends on: TICKET-047, TICKET-055
Status: Done

## Goal

Rework Phase 2 permissions into explicit request, granted, denied, settings,
and retry branches for camera, microphone, and text/paste/input permissions.

## System dependencies

- Windows privacy settings for camera and microphone.
- macOS privacy permissions for camera, microphone, Accessibility, and Input
  Monitoring where applicable.
- Electron permission helpers exposed through the preload bridge.

## Python packages

None.

## Work

- Split the current generic `PermissionProbeStep` behavior into a clearer
  permission state machine for each permission:
  - Not requested.
  - Requesting.
  - Granted.
  - Denied or unavailable.
  - Open settings.
  - Retry.
- Keep `probe.run` as the hardware verification source for camera and mic, but
  add OS-level permission status where Electron exposes it.
- Use the existing `permissions.mediaStatus` bridge for macOS camera/mic status
  where useful, instead of leaving it unused.
- Add explicit denial branch copy for each permission, including what the user
  should change in OS settings.
- Add retry controls that return the user to the relevant permission request
  after OS settings are changed.
- Add a dedicated text/paste/input permission step that explains clipboard paste,
  global shortcut input, and Accessibility/Input Monitoring requirements by
  platform.
- Decide whether each permission is a hard gate or has an explicit degraded-mode
  path, and encode that behavior in the ticket implementation.
- Ensure the wizard does not show dashboard-only account/probe panels during
  permission flow.
- Add component tests for granted, denied, retry, and unavailable branches on
  Windows and macOS.

## Implemented (2026-05)

- Added `permissions.requestMediaAccess` through `desktop/electron/main.ts`,
  `desktop/electron/preload.cts`, and `desktop/renderer/src/types/window.d.ts`
  for macOS camera/microphone requests.
- Expanded `platform.openPrivacySettings` to support `camera`, `microphone`,
  `accessibility`, and `input-monitoring`, preserving Windows privacy URIs and
  adding macOS System Settings URLs.
- Added `desktop/renderer/src/onboarding/permissionState.ts` to classify OS
  permission status separately from hardware probe status.
- Reworked `desktop/renderer/src/onboarding/PermissionProbeStep.tsx` so camera
  and microphone steps show OS permission status, hardware probe status,
  denial/failure copy, settings links, retry controls, and disabled `Next` until
  verified.
- Reworked `desktop/renderer/src/onboarding/AccessibilityStep.tsx` into a
  platform-aware text/paste/input permission step. macOS Accessibility is gated;
  Windows explains shortcut/paste behavior and can continue.
- Wired the new permission helpers through
  `desktop/renderer/src/onboarding/OnboardingWizard.tsx`.
- Updated renderer test bridge mocks and expanded
  `desktop/renderer/src/onboarding/__tests__/OnboardingWizard.test.tsx` to cover
  Windows success/failure, macOS denial/granted media status, macOS
  Accessibility gating, and Windows input permission continuation.
- Verification: `npm test -- OnboardingWizard.test.tsx`, `npm run typecheck`,
  and `npm run lint` under `desktop/` all pass.

## Acceptance criteria

- [x] Camera permission has visible request, success, denial, settings, and retry
      states.
- [x] Microphone permission has visible request, success, denial, settings, and
      retry states.
- [x] Text/paste/input permissions are explained in a dedicated onboarding step
      with platform-specific copy.
- [x] Windows users get working deep links to Camera and Microphone privacy
      settings.
- [x] macOS users get appropriate System Settings guidance for Camera,
      Microphone, Accessibility, and Input Monitoring.
- [x] Denied permissions do not strand the user; every denied branch has a clear
      retry path.
- [x] The implementation distinguishes OS permission status from hardware probe
      failures in user-facing copy.
- [x] Component tests cover success, denial, settings, retry, and unsupported
      platform states.

## Out of scope

- Camera/mic device selection; TICKET-058 owns choosing and changing devices.
- Calibration capture; TICKET-059 owns calibration success and retry.
- Silent installation or automatic modification of OS privacy settings.

## References

- `desktop/renderer/src/onboarding/PermissionProbeStep.tsx` - permission/probe
  branching step.
- `desktop/renderer/src/onboarding/AccessibilityStep.tsx` - text/paste/input
  permission copy.
- `desktop/renderer/src/onboarding/permissionState.ts` - permission state
  classification helpers.
- `desktop/renderer/src/onboarding/probe.ts` - probe result interpretation.
- `desktop/electron/preload.cts` - permission bridge surface.
- `desktop/electron/main.ts` - platform permission helpers and privacy links.
- `tickets/distribution_packaging/TICKET-047-onboarding-permissions-wizard.md`
  - completed first-launch wizard baseline.
