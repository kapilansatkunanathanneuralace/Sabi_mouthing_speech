import { useState } from "react";

import type { ProbeResponse } from "../types/sidecar";
import { nextStep } from "./steps";
import { probePassed, probeSummary } from "./probe";
import type { ProbeStepProps, ProbeTarget } from "./types";

interface Props extends ProbeStepProps {
  target: ProbeTarget;
  title: string;
}

export function PermissionProbeStep({
  callProbe,
  goTo,
  openPrivacySettings,
  platform,
  target,
  title
}: Props) {
  const [result, setResult] = useState<ProbeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const passed = result ? probePassed(result, target) : false;

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setResult(await callProbe());
    } catch (probeError) {
      setError(probeError instanceof Error ? probeError.message : String(probeError));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="wizard-step">
      <h2>{title}</h2>
      <p>Run a hardware probe so Sabi can verify this permission before continuing.</p>
      <div className={`check-card ${passed ? "check-pass" : "check-pending"}`}>
        <strong>{passed ? "Passed" : "Not verified"}</strong>
        <span>{result ? probeSummary(result, target) : "Probe has not run yet."}</span>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button type="button" onClick={() => void run()} disabled={running}>
          {running ? "Checking..." : "Run probe"}
        </button>
        {platform.isWindows ? (
          <button type="button" onClick={() => void openPrivacySettings(target)}>
            Open Windows privacy settings
          </button>
        ) : null}
        <button type="button" disabled={!passed} onClick={() => void goTo(nextStep(target, platform))}>
          Next
        </button>
      </div>
    </div>
  );
}
