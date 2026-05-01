import { type ChangeEvent, type FormEvent, useState } from "react";

import { useSupabaseAuth } from "../supabase/useSupabaseAuth";
import { getSupabase } from "../supabaseClient";
import type { DesktopSettings, OnboardingProfileDraft } from "../types/sidecar";
import type { StepProps } from "./types";

interface Props extends StepProps {
  settings: DesktopSettings;
}

const referralOptions = [
  ["friend", "Friend or colleague"],
  ["search", "Search"],
  ["social", "Social media"],
  ["community", "Community or forum"],
  ["other", "Other"]
] as const;

const useCaseOptions = [
  ["silent_dictation", "Silent dictation"],
  ["audio_dictation", "Audio dictation"],
  ["meetings", "Meetings"],
  ["accessibility", "Accessibility"],
  ["experimentation", "Experimentation"]
] as const;

const workEnvironmentOptions = [
  ["office", "Office"],
  ["home", "Home"],
  ["hybrid", "Hybrid"],
  ["public_spaces", "Public spaces"],
  ["other", "Other"]
] as const;

const emptyDraft: OnboardingProfileDraft = {
  referralSource: "",
  profession: "",
  useCases: [],
  workEnvironment: "",
  updatedAt: ""
};

export function ProfileIntakeStep({ goTo, settings }: Props) {
  const { session } = useSupabaseAuth();
  const [draft, setDraft] = useState<OnboardingProfileDraft>(
    settings.onboardingProfileDraft ?? emptyDraft
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function persistDraft(next: OnboardingProfileDraft) {
    await window.sabi?.settings.update({ onboardingProfileDraft: next });
  }

  async function updateDraft(patch: Partial<OnboardingProfileDraft>) {
    const next = { ...draft, ...patch, updatedAt: new Date().toISOString() };
    setDraft(next);
    setMessage(null);
    await persistDraft(next);
  }

  function validationMessage(): string | null {
    if (!draft.referralSource) {
      return "Choose how you heard about Sabi.";
    }
    if (!draft.profession.trim()) {
      return "Enter your profession.";
    }
    if (draft.useCases.length === 0) {
      return "Choose at least one use case.";
    }
    if (!draft.workEnvironment) {
      return "Choose your work environment.";
    }
    return null;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validationMessage();
    if (invalid) {
      setMessage(invalid);
      return;
    }
    const userId = session?.user?.id;
    if (!userId) {
      setMessage("Sign in again before saving profile details.");
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      const { error } = await getSupabase()
        .from("user_onboarding_intake")
        .upsert(
          {
            user_id: userId,
            referral_source: draft.referralSource,
            profession: draft.profession.trim(),
            use_cases: draft.useCases,
            work_environment: draft.workEnvironment
          },
          { onConflict: "user_id" }
        );
      if (error) {
        setMessage(`Profile sync failed: ${error.message}`);
        return;
      }
      await window.sabi?.settings.update({ onboardingProfileDraft: null });
      await goTo("welcome");
    } catch (error) {
      setMessage(`Profile sync failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  }

  async function toggleUseCase(event: ChangeEvent<HTMLInputElement>) {
    const { checked, value } = event.target;
    const useCases = checked
      ? [...draft.useCases, value]
      : draft.useCases.filter((item) => item !== value);
    await updateDraft({ useCases });
  }

  return (
    <div className="wizard-step">
      <h2>Tell us how you will use Sabi</h2>
      <p>
        These answers help tailor onboarding and support. You can retry sync without losing input.
      </p>
      <form className="supabase-form" noValidate onSubmit={(event) => void submit(event)}>
        <label>
          How did you hear about Sabi?
          <select
            required
            value={draft.referralSource}
            onChange={(event) => void updateDraft({ referralSource: event.target.value })}
          >
            <option value="">Choose one</option>
            {referralOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Profession
          <input
            required
            value={draft.profession}
            onChange={(event) => void updateDraft({ profession: event.target.value })}
            placeholder="Designer, engineer, student..."
          />
        </label>
        <fieldset>
          <legend>Use cases</legend>
          {useCaseOptions.map(([value, label]) => (
            <label key={value} className="checkbox">
              <input
                type="checkbox"
                value={value}
                checked={draft.useCases.includes(value)}
                onChange={(event) => void toggleUseCase(event)}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <label>
          Work environment
          <select
            required
            value={draft.workEnvironment}
            onChange={(event) => void updateDraft({ workEnvironment: event.target.value })}
          >
            <option value="">Choose one</option>
            {workEnvironmentOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button disabled={saving} type="submit">
          {saving ? "Saving..." : "Continue"}
        </button>
      </form>
      {message ? <p className="error">{message}</p> : null}
    </div>
  );
}
