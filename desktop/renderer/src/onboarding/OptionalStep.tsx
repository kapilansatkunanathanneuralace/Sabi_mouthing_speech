import { nextStep } from "./steps";
import type { StepProps } from "./types";

export function OptionalStep({ goTo, platform }: StepProps) {
  return (
    <div className="wizard-step">
      <h2>Optional setup</h2>
      <p>
        Ollama improves cleanup quality, and virtual microphone drivers enable future meeting mode.
        You can skip both and still use local dictation.
      </p>
      <ul className="wizard-list">
        <li>
          Ollama: see <code>docs/INSTALL.md</code>.
        </li>
        <li>
          Virtual mic: {platform.isMac ? "BlackHole instructions are a future docs item." : "see docs/INSTALL-VBCABLE.md."}
        </li>
      </ul>
      <div className="actions">
        <button type="button" onClick={() => void goTo(nextStep("optional", platform))}>
          Skip optional setup
        </button>
      </div>
    </div>
  );
}
