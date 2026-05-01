# TICKET-059 - Calibration flow

Phase: 4 - User Interface Flow
Epic: UX
Estimate: L
Depends on: TICKET-058
Status: Done

## Goal

Add optional Phase 3 calibration onboarding for three random sentence samples,
with clear success, skip, cancel, and retry paths before launching the main app.

## System dependencies

- Camera, microphone, device, and shortcut checks from TICKET-058.
- Full dictation runtime and model assets installed.
- Sidecar calibration or dry-run APIs capable of labeled capture attempts.

## Python packages

None expected. If implementation requires a new calibration helper package, add
it explicitly in this ticket before coding.

## Work

- Define calibration sample behavior:
  - Three random sentence samples.
  - Optional start/skip branch.
  - Read or silently mouth the displayed prompt.
- Define the minimum success criteria for each sample type:
  - Capture completed.
  - Camera/mic input usable for the requested mode.
  - Pipeline returned non-empty or otherwise valid calibration output.
  - Confidence or quality threshold if one exists.
- Add sidecar API methods or extend existing dictation dry-run calls so the
  renderer can request labeled calibration attempts and receive structured
  pass/fail details.
- Build onboarding UI for each calibration step with:
  - Prompt text.
  - Start/stop controls.
  - Live status.
  - Success state.
  - Retry branch.
  - Failure explanation.
- Decide what calibration artifacts are stored:
  - Local-only transient quality checks.
  - Local calibration metadata.
  - Optional Supabase summary fields.
  - Explicitly never-uploaded raw audio/video unless a future consent ticket
    changes that.
- Add privacy copy before capture begins, especially for face and voice data.
- Ensure failed calibration lets the user retry the same step without resetting
  earlier successful steps.
- Add completion behavior that transitions to the final launch/polish ticket
  flow rather than directly showing the old `done` screen.
- Add tests for pass, fail, retry, cancellation, and resume behavior.

## Acceptance criteria

- [x] Users can skip optional calibration and continue setup.
- [x] Users can complete three random sentence calibration samples with
      success/retry feedback.
- [x] Each failed sample explains the likely issue and offers retry without
      losing prior successful samples.
- [x] Users can cancel a calibration attempt.
- [x] The renderer receives structured calibration results from the sidecar,
      not ad hoc parsed strings.
- [x] Privacy copy states what is stored locally, what is synced, and what is
      never uploaded.
- [x] Raw calibration audio/video is not uploaded without a separate explicit
      consent ticket.
- [x] Calibration progress persists across app relaunch.
- [x] Component and sidecar-contract tests cover success, failure, retry, and
      cancellation.

## Implemented

- Added persisted calibration progress metadata to desktop settings.
- Added `calibration.plan`, `calibration.run`, and `calibration.cancel` sidecar
  handlers with structured responses.
- Added optional calibration intro, sample runner, and summary onboarding steps.
- Wired calibration after model setup and before the final launch/polish path.
- Added tests for skip, random sample planning, pass, fail, retry, cancellation,
  resume, and sidecar response contracts.

## Out of scope

- Model fine-tuning from calibration data.
- Uploading raw calibration media.
- Personal adaptation dataset export.
- Meeting-mode voice cloning.

## References

- `desktop/renderer/src/App.tsx` - current post-onboarding dry-run action.
- `desktop/renderer/src/onboarding/OnboardingWizard.tsx` - target wizard
  orchestration.
- `src/sabi/pipelines/silent_dictate.py` - silent dictation pipeline behavior.
- `src/sabi/pipelines/audio_dictate.py` - audio dictation pipeline behavior.
- `tickets/fusion_eval_fine_tuning/TICKET-034-personal-adaptation-dataset-export.md`
  - future dataset export boundary.
- `tickets/fusion_eval_fine_tuning/TICKET-032-fused-confidence-calibration.md`
  - confidence calibration boundary.
