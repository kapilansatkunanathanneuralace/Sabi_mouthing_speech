# TICKET-058 - Device and shortcut checks

Phase: 4 - User Interface Flow
Epic: UX
Estimate: L
Depends on: TICKET-057
Status: Done

## Goal

Add the Phase 2 device and input checks from the UI flow: camera check, change
camera, microphone check, change microphone, keyboard shortcut setup, change
shortcut, and shortcut success validation.

## System dependencies

- Camera and microphone permissions from TICKET-057.
- Electron APIs for media device enumeration where available.
- Electron global shortcut registration.
- Python sidecar probe support for selected camera and microphone devices.

## Python packages

None.

## Work

- Add selected camera and microphone settings to the desktop settings schema, or
  define a separate persisted onboarding device preference store.
- Extend the Electron/preload bridge to enumerate available cameras and
  microphones if the renderer cannot rely on browser media APIs in the packaged
  app.
- Extend sidecar probe calls so camera and microphone checks can target the
  selected device, not only camera index `0` and the default audio input.
- Build onboarding UI for:
  - Camera check.
  - Change camera.
  - Camera success/failure branch.
  - Microphone check.
  - Change microphone.
  - Microphone success/failure branch.
  - Keyboard shortcut setup.
  - Change shortcut.
  - Shortcut success/failure branch.
- Validate global shortcut conflicts before accepting a shortcut where Electron
  can detect registration failure.
- Add a shortcut test mode that asks the user to press the configured shortcut
  and confirms the app receives it.
- Persist selected devices and shortcut choices before leaving Phase 2.
- Keep copy clear about the current Electron push-to-talk limitation: repeated
  shortcut presses start/stop because Electron global shortcuts do not emit
  key-release events.
- Add tests for device list loading, device switching, probe calls using the
  selected device, shortcut conflict handling, and successful shortcut capture.

## Acceptance criteria

- [x] Users can see the currently selected camera and run a camera check.
- [x] Users can change cameras and rerun the check without restarting
      onboarding.
- [x] Users can see the currently selected microphone and run a microphone
      check.
- [x] Users can change microphones and rerun the check without restarting
      onboarding.
- [x] Camera and microphone probe calls use the selected device where the
      sidecar supports it.
- [x] Users can choose a keyboard shortcut during onboarding.
- [x] Shortcut conflicts or registration failures are shown with a change/retry
      path.
- [x] Users must successfully trigger the selected shortcut before leaving the
      shortcut step.
- [x] Device and shortcut choices persist across app relaunch.
- [x] Component and bridge tests cover the device and shortcut paths.

## Implemented

- Added persisted `cameraIndex`, `microphoneDeviceIndex`, and
  `shortcutVerified` desktop settings.
- Added sidecar `probe.devices` plus targeted `probe.run` audio device support.
- Added Electron shortcut validation and press-to-confirm test IPC.
- Added camera device, microphone device, and shortcut onboarding steps.
- Wired selected devices into onboarding probes and dashboard probe calls.
- Added Python, Electron, and renderer tests for device selection, probe
  parameters, shortcut conflicts, and shortcut confirmation.

## Out of scope

- Permission request/denial branches; TICKET-057 owns those.
- Calibration sample collection; TICKET-059 owns calibration.
- Advanced per-app shortcut profiles.
- Meeting-mode mute shortcut behavior.

## References

- `desktop/renderer/src/onboarding/PermissionProbeStep.tsx` - current camera/mic
  probe UI.
- `desktop/renderer/src/onboarding/probe.ts` - current probe pass/fail parsing.
- `desktop/electron/settings.ts` - persisted desktop settings.
- `desktop/electron/shortcuts.ts` - current global shortcut registration.
- `docs/distribution_packaging/HOTKEY_OWNERSHIP.md` - shortcut ownership notes.
- `src/sabi/probe.py` - sidecar probe source of truth.
