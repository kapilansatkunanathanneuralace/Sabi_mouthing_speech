# TICKET-056 - Profile intake questions

Phase: 4 - User Interface Flow
Epic: UX
Estimate: M
Depends on: TICKET-055
Status: Done

## Goal

Add Phase 1 profile intake screens after required account authentication,
capturing referral source, profession, intended use cases, and work environment
before moving into permissions.

## System dependencies

- Supabase Auth session from TICKET-055.
- Supabase database table or tables for onboarding/profile answers, with RLS.

## Python packages

None.

## Work

- Define the canonical answer schema for:
  - Referral source.
  - Profession.
  - Use cases.
  - Work environment.
- Decide and document which fields are single-select, multi-select, free text,
  or "Other" with a text value.
- Create onboarding step components under `desktop/renderer/src/onboarding/`
  for each question or a grouped profile form, matching the existing wizard
  styling.
- Add client-side validation so required answers are complete before advancing.
- Persist answers locally enough to resume after quitting mid-flow.
- Sync answers to Supabase using authenticated user context only after the user
  completes or advances each profile step.
- Add or update Supabase schema through a migration when implementation begins:
  - Enable RLS on any exposed table.
  - Use policies tied to `auth.uid()`.
  - Do not rely on user-editable JWT metadata for authorization.
- Add loading, retry, and failure states for profile sync. Users should not lose
  completed form input when a sync fails.
- Add component tests for validation, persistence, retry, and successful
  progression to permissions.

## Implemented (2026-05)

- Added `docs/supabase/user-onboarding-intake.sql` for
  `public.user_onboarding_intake`, including per-user RLS policies, grants, and
  an `updated_at` trigger.
- Added `profile` to the onboarding step model in
  `desktop/renderer/src/types/sidecar.ts`, `desktop/electron/settings.ts`, and
  `desktop/renderer/src/onboarding/steps.ts`.
- Added `onboardingProfileDraft` to desktop settings so intake answers persist
  locally before Supabase sync succeeds.
- Added `desktop/renderer/src/onboarding/ProfileIntakeStep.tsx` with required
  referral source, profession, use cases, and work environment inputs.
- Profile intake writes local drafts through `window.sabi.settings.update`,
  syncs the current authenticated user to Supabase with `upsert`, shows sync
  failures without clearing form input, and clears the local draft after a
  successful sync.
- `AccountStep` now continues to `profile`, `OnboardingWizard` renders the
  profile step, and `WelcomeStep` uses `nextStep` so future step ordering is not
  bypassed.
- Expanded `OnboardingWizard.test.tsx` coverage for validation, local draft
  persistence, saved draft resume, successful Supabase sync, failed sync retry,
  and updated account-to-profile ordering.
- Verification: `npm test -- OnboardingWizard.test.tsx`, `npm run typecheck`,
  and `npm run lint` under `desktop/` all pass.

## Acceptance criteria

- [x] Authenticated users see Phase 1 profile/intake screens before any
      permission prompts.
- [x] Referral source, profession, use cases, and work environment are all
      captured with clear labels and accessible form controls.
- [x] Required fields block progression until valid.
- [x] Answers persist across renderer reload or app quit before submission.
- [x] Supabase sync writes only for the current authenticated user.
- [x] All exposed Supabase tables involved have RLS enabled and scoped policies.
- [x] Sync errors show a retry path without clearing user input.
- [x] Component tests cover validation, resume, successful sync, and sync
      failure.

## Out of scope

- Account creation and session gating; TICKET-055 owns auth.
- Product analytics dashboards for questionnaire answers.
- Editing answers after onboarding from the dashboard.
- Calibration data capture; TICKET-059 owns calibration artifacts.

## References

- `desktop/renderer/src/onboarding/OnboardingWizard.tsx` - wizard orchestration.
- `desktop/renderer/src/onboarding/ProfileIntakeStep.tsx` - profile intake UI.
- `desktop/renderer/src/types/sidecar.ts` - onboarding settings/types.
- `desktop/electron/settings.ts` - persisted desktop settings schema.
- `docs/supabase/user-onboarding-intake.sql` - profile intake table and RLS.
- `desktop/renderer/src/SupabasePanel.tsx` - current profile preview behavior.
- Supabase RLS and Auth docs - verify current best practices before schema work.
