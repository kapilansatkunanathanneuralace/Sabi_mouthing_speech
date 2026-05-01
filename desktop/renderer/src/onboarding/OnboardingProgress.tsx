import type { OnboardingStep } from "../types/sidecar";
import { onboardingPhases, phaseProgress } from "./steps";

interface Props {
  step: OnboardingStep;
}

export function OnboardingProgress({ step }: Props) {
  const progress = phaseProgress(step);
  return (
    <div className="wizard-progress" aria-label="Onboarding progress">
      <div className="wizard-phases">
        {onboardingPhases.map((phase, index) => (
          <span
            key={phase.id}
            className={index === progress.phaseIndex ? "active" : ""}
          >
            {phase.label}
          </span>
        ))}
      </div>
      <p>
        {progress.phase.label} · Step {progress.substepNumber} of {progress.substepTotal}:{" "}
        {progress.substepLabel}
      </p>
    </div>
  );
}
