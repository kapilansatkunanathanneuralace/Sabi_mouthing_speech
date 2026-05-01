import { useState } from "react";

import { statusClass, type PermissionState } from "./permissionState";
import { nextStep } from "./steps";
import type { StepProps } from "./types";

interface Props extends StepProps {
  openPrivacySettings: (target: "accessibility" | "input-monitoring") => Promise<void>;
}

export function AccessibilityStep({ goTo, openPrivacySettings, platform }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [state, setState] = useState<PermissionState>(platform.isMac ? "idle" : "unsupported");
  const canContinue = !platform.isMac || state === "granted";

  async function checkAccessibility(prompt: boolean) {
    if (!window.sabi) {
      setMessage("Electron permission helpers are unavailable in browser preview.");
      setState("error");
      return;
    }
    setState("checking");
    const result = await window.sabi.permissions.accessibilityStatus(prompt);
    setState(result.supported ? (result.granted ? "granted" : "denied") : "unsupported");
    setMessage(
      result.supported
        ? result.granted
          ? "Accessibility permission is granted."
          : "Accessibility permission is not granted yet. Open settings, grant access, then retry."
        : "Accessibility permission is not required on this platform."
    );
  }

  return (
    <div className="wizard-step">
      <h2>Text, paste, and input permissions</h2>
      {platform.isMac ? (
        <p>
          macOS requires Accessibility for reliable shortcuts and paste automation. You may also
          need Input Monitoring enabled in System Settings.
        </p>
      ) : (
        <p>
          Windows does not require a separate Accessibility permission. Sabi uses the configured
          global shortcut and clipboard paste when dictation is accepted.
        </p>
      )}
      <div className={`check-card ${statusClass(state)}`}>
        <strong>
          {state === "granted"
            ? "Input permission granted"
            : state === "unsupported"
              ? "No extra permission required"
              : state === "denied"
                ? "Input permission denied"
                : state === "checking"
                  ? "Checking input permission"
                  : "Input permission not checked"}
        </strong>
        <span>{message ?? "Run the check before continuing."}</span>
      </div>
      <div className="actions">
        {platform.isMac ? (
          <>
            <button type="button" onClick={() => void checkAccessibility(true)}>
              Check permission
            </button>
            <button type="button" onClick={() => void openPrivacySettings("accessibility")}>
              Open Accessibility settings
            </button>
            <button type="button" onClick={() => void openPrivacySettings("input-monitoring")}>
              Open Input Monitoring settings
            </button>
          </>
        ) : (
          <button type="button" onClick={() => void checkAccessibility(false)}>
            Review permission
          </button>
        )}
        <button
          type="button"
          disabled={!canContinue}
          onClick={() => void goTo(nextStep("accessibility", platform))}
        >
          Continue
        </button>
      </div>
    </div>
  );
}
