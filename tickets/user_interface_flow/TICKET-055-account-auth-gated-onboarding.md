# TICKET-055 - Account auth gated onboarding

Phase: 4 - User Interface Flow
Epic: UX
Estimate: M
Depends on: TICKET-047
Status: Done

## Goal

Make account sign-up or sign-in the required first step of desktop onboarding, so
new users cannot proceed to profile intake, permissions, devices, or calibration
until a valid Supabase session exists.

## System dependencies

- Supabase project with Auth enabled.
- Desktop renderer configured with `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_PUBLISHABLE_KEY`.
- Network connectivity for sign-up, sign-in, and session refresh.

## Python packages

None.

## Work

- Verify current Supabase Auth guidance before implementation, especially
  session persistence, email confirmation behavior, and publishable-key usage.
- Move the account UI from the always-visible `SupabasePanel` surface into the
  first onboarding step under `desktop/renderer/src/onboarding/`.
- Keep the existing dashboard account panel available after onboarding, but do
  not render it above the wizard while onboarding is active.
- Extend the onboarding step model in `desktop/renderer/src/types/sidecar.ts`
  and `desktop/electron/settings.ts` with an account/auth step.
- Gate all later onboarding steps on a valid Supabase session from
  `useSupabaseAuth`.
- Show explicit blocking states for:
  - Supabase env vars missing.
  - Auth provider initializing.
  - Email confirmation required.
  - Network/auth errors.
- Preserve session restore on app relaunch so confirmed users resume at the
  next saved onboarding step.
- Add renderer tests for required auth, successful sign-up/sign-in, missing
  Supabase config, and resume-after-session-restore.

## Implemented (2026-05)

- Added persisted onboarding step `account` as the first step in
  `desktop/renderer/src/types/sidecar.ts`, `desktop/electron/settings.ts`
  (default `onboardingStep: "account"`), and `desktop/renderer/src/onboarding/steps.ts`.
- New `desktop/renderer/src/onboarding/AccountStep.tsx`: sign-in / create-account
  form using `useSupabaseAuth`; blocking copy when Supabase env is missing;
  initializing copy; post-sign-up message when email confirmation is required
  (`confirmationHint` from existing `SupabaseAuthProvider`); signed-in state with
  **Continue** to `welcome`.
- `desktop/renderer/src/onboarding/OnboardingWizard.tsx`: uses `useSupabaseAuth`;
  `visibleStep` forces `account` when there is no `session?.user`; effect resets
  persisted step to `account` if settings point past account but user is signed
  out; progress UI highlights the effective step.
- `desktop/renderer/src/App.tsx`: `SupabasePanel` removed from above the
  onboarding branch; rendered inside `Dashboard` only after onboarding completes
  (account status and sign-out unchanged for completed users).
- `SupabasePanel.tsx` was not refactored into a shared component; onboarding uses
  `AccountStep` with the same auth APIs. Dashboard still uses `SupabasePanel` for
  profile preview and sign-out.
- Tests: `desktop/renderer/src/onboarding/__tests__/OnboardingWizard.test.tsx`
  wraps the wizard in `SupabaseAuthContext.Provider` with mocks; covers account
  first screen, missing config, continue when signed in, redirect to account
  from a later step when signed out, sign-in submit, and existing wizard flows.
- Verification: `npm test -- OnboardingWizard.test.tsx`, `npm run typecheck`, and
  `npm run lint` under `desktop/` all pass.

## Acceptance criteria

- [x] Fresh first launch starts on the account step before any profile,
      permission, model, device, or calibration screens.
- [x] Users cannot advance past the account step without a valid Supabase
      session.
- [x] Missing Supabase configuration produces a clear blocking message with the
      exact required env vars and does not crash the renderer.
- [x] Email-confirmation-required projects show copy telling the user to confirm
      before continuing.
- [x] Existing signed-in users resume from their saved onboarding step without
      seeing the account form again.
- [x] The dashboard still exposes account status and sign-out after onboarding.
- [x] No service-role or secret Supabase key is used or exposed in renderer code.
- [x] Component tests cover the account gate and pass.

## Out of scope

- Social login providers.
- Password reset and account recovery flows.
- Offline account creation.
- Profile questionnaire storage; TICKET-056 owns profile/intake data.

## References

- `desktop/renderer/src/onboarding/AccountStep.tsx` - onboarding account gate UI.
- `desktop/renderer/src/SupabasePanel.tsx` - dashboard account panel (post-onboarding).
- `desktop/renderer/src/supabase/useSupabaseAuth.ts` - auth state hook.
- `desktop/renderer/src/onboarding/OnboardingWizard.tsx` - wizard orchestration and session gate.
- `desktop/electron/settings.ts` - persisted onboarding step schema.
- Supabase Auth docs - verify current API behavior when extending auth flows.
