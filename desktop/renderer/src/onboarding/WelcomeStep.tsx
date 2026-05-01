import { nextStep } from "./steps";
import type { StepProps } from "./types";

export function WelcomeStep({ goTo, platform }: StepProps) {
  return (
    <div className="wizard-step">
      <h2>Welcome to Sabi</h2>
      <p>
        This local setup checks camera, microphone, permissions, and model assets before your
        first dictation run.
      </p>
      <button type="button" onClick={() => void goTo(nextStep("welcome", platform))}>
        Start setup
      </button>
    </div>
  );
}
