import { useState } from "react";

import type { ProbeResponse } from "../types/sidecar";
import { classifyMediaStatus, statusClass, type PermissionState } from "./permissionState";
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
  mediaStatus,
  openPrivacySettings,
  platform,
  requestMediaAccess,
  target,
  title
}: Props) {
  const [result, setResult] = useState<ProbeResponse | null>(null);
  const [osState, setOsState] = useState<PermissionState>("idle");
  const [osDetail, setOsDetail] = useState("Permission has not been checked yet.");
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const passed = result ? probePassed(result, target) : false;
  const probeState: PermissionState = result ? (passed ? "granted" : "probe_failed") : "idle";
  const canProceed = passed && (osState === "granted" || osState === "unsupported");

  async function runProbe() {
    const probeResult = await callProbe();
    setResult(probeResult);
    if (!probePassed(probeResult, target)) {
      setError(`${title} hardware check failed. ${probeSummary(probeResult, target)}`);
    }
  }

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    setOsState("checking");
    setOsDetail("Checking OS permission...");
    try {
      if (platform.isMac) {
        const status = await mediaStatus(target);
        let classified = classifyMediaStatus(status.status, platform);
        if (status.supported && classified.state === "idle") {
          const requested = await requestMediaAccess(target);
          classified = requested.granted
            ? { state: "granted", detail: "OS permission was granted." }
            : {
                state: "denied",
                detail: "OS permission was not granted. Open settings, grant access, then retry."
              };
        }
        setOsState(classified.state);
        setOsDetail(classified.detail);
        if (classified.state !== "granted" && classified.state !== "unsupported") {
          return;
        }
      } else {
        setOsState("unsupported");
        setOsDetail("No separate OS permission status is available here; using hardware probe.");
      }
      await runProbe();
    } catch (probeError) {
      setOsState("error");
      setError(probeError instanceof Error ? probeError.message : String(probeError));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="wizard-step">
      <h2>{title}</h2>
      <p>
        Sabi checks OS permission first, then verifies the {target} with a hardware probe.
      </p>
      <div className={`check-card ${statusClass(osState)}`}>
        <strong>
          {osState === "granted"
            ? "OS permission granted"
            : osState === "unsupported"
              ? "OS permission check unavailable"
              : osState === "denied"
                ? "OS permission denied"
                : osState === "checking"
                  ? "Checking permission"
                  : "OS permission not verified"}
        </strong>
        <span>{osDetail}</span>
      </div>
      <div className={`check-card ${statusClass(probeState)}`}>
        <strong>
          {passed ? "Hardware probe passed" : result ? "Hardware probe failed" : "Probe not run"}
        </strong>
        <span>{result ? probeSummary(result, target) : "Probe runs after permission is available."}</span>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button type="button" onClick={() => void run()} disabled={running}>
          {running ? "Checking..." : result || osState === "denied" ? "Retry check" : "Request / Check access"}
        </button>
        {platform.isWindows || platform.isMac ? (
          <button type="button" onClick={() => void openPrivacySettings(target)}>
            Open {platform.isMac ? "System Settings" : "Windows privacy settings"}
          </button>
        ) : null}
        <button type="button" disabled={!canProceed} onClick={() => void goTo(nextStep(target, platform))}>
          Next
        </button>
      </div>
    </div>
  );
}
