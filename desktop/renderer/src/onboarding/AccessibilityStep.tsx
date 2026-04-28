import { useState } from "react";

import { nextStep } from "./steps";
import type { StepProps } from "./types";

export function AccessibilityStep({ goTo, platform }: StepProps) {
  const [message, setMessage] = useState<string | null>(null);

  async function checkAccessibility(prompt: boolean) {
    if (!window.sabi) {
      setMessage("Electron permission helpers are unavailable in browser preview.");
      return;
    }
    const result = await window.sabi.permissions.accessibilityStatus(prompt);
    setMessage(
      result.supported
        ? `Accessibility permission: ${result.granted ? "granted" : "not granted yet"}`
        : "Accessibility permission is not required on this platform."
    );
  }

  return (
    <div className="wizard-step">
      <h2>Accessibility and input permissions</h2>
      {platform.isMac ? (
        <p>
          macOS may require Accessibility and Input Monitoring permissions before global shortcuts
          work reliably.
        </p>
      ) : (
        <p>Windows does not require an extra Accessibility permission for Sabi shortcuts.</p>
      )}
      {message ? <div className="check-card check-pending">{message}</div> : null}
      <div className="actions">
        <button type="button" onClick={() => void checkAccessibility(true)}>
          Check permission
        </button>
        <button type="button" onClick={() => void goTo(nextStep("accessibility", platform))}>
          Continue
        </button>
      </div>
    </div>
  );
}
