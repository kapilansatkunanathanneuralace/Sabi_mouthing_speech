import type { DoneStepProps } from "./types";

export function DoneStep({ complete }: DoneStepProps) {
  return (
    <div className="wizard-step">
      <h2>Setup complete</h2>
      <p>Sabi is ready for a first silent dictation run.</p>
      <button type="button" onClick={() => void complete()}>
        Finish onboarding
      </button>
    </div>
  );
}
