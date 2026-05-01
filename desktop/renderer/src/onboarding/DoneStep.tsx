import type { DoneStepProps } from "./types";

export function DoneStep({ complete, settings }: DoneStepProps) {
  return (
    <div className="wizard-step">
      <h2>Launch Sabi</h2>
      <p>
        Setup is complete. Your shortcut is <strong>{settings.hotkey}</strong>, your pipeline is{" "}
        <strong>{settings.pipeline}</strong>, and the main dashboard will open next.
      </p>
      <p>
        You can change devices, shortcut mode, model cache, and account status from the dashboard
        after launch.
      </p>
      <div className="actions">
        <button type="button" onClick={() => void complete()}>
          Launch Sabi
        </button>
      </div>
    </div>
  );
}
