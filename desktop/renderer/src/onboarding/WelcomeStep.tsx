import type { StepProps } from "./types";

export function WelcomeStep({ goTo }: StepProps) {
  return (
    <div className="wizard-step">
      <h2>Welcome to Sabi</h2>
      <p>
        This local setup checks camera, microphone, permissions, and model assets before your
        first dictation run.
      </p>
      <button type="button" onClick={() => void goTo("camera")}>
        Start setup
      </button>
    </div>
  );
}
