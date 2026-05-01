import { useState } from "react";

import type {
  CalibrationRunResponse,
  DesktopSettings,
  DesktopSettingsPatch
} from "../types/sidecar";
import { nextStep } from "./steps";
import {
  applyCalibrationResult,
  emptyCalibrationProgress,
  markCalibrationCancelled
} from "./calibration";
import type { StepProps } from "./types";

interface Props extends StepProps {
  callCancel: () => Promise<void>;
  callRun: (sample: { sampleId: string; text: string }) => Promise<CalibrationRunResponse>;
  settings: DesktopSettings;
  updateSettings: (patch: DesktopSettingsPatch) => Promise<DesktopSettings | undefined>;
}

export function CalibrationSampleStep({
  callCancel,
  callRun,
  goTo,
  platform,
  settings,
  updateSettings
}: Props) {
  const [running, setRunning] = useState(false);
  const progress = settings.calibrationProgress ?? emptyCalibrationProgress();
  const sample = progress.samples.find((item) => item.status !== "passed");
  const completedCount = progress.samples.filter((item) => item.status === "passed").length;

  async function runSample() {
    if (!sample) {
      await goTo("calibrationSummary");
      return;
    }
    setRunning(true);
    try {
      const result = await callRun(sample);
      const nextProgress = applyCalibrationResult(progress, result);
      await updateSettings({ calibrationProgress: nextProgress });
      if (nextProgress.completed) {
        await goTo("calibrationSummary");
      }
    } finally {
      setRunning(false);
    }
  }

  async function cancelSample() {
    if (!sample) {
      return;
    }
    await callCancel();
    await updateSettings({
      calibrationProgress: markCalibrationCancelled(progress, sample.sampleId)
    });
  }

  if (!sample) {
    return (
      <div className="wizard-step">
        <h2>Calibration samples complete</h2>
        <p>All three optional calibration samples have passed.</p>
        <button type="button" onClick={() => void goTo(nextStep("calibrationSample", platform))}>
          Continue
        </button>
      </div>
    );
  }

  const sampleNumber = progress.samples.findIndex((item) => item.sampleId === sample.sampleId) + 1;

  return (
    <div className="wizard-step">
      <h2>Calibration sample {sampleNumber} of {progress.samples.length}</h2>
      <p>Read or silently mouth this sentence when you start the sample:</p>
      <blockquote>{sample.text}</blockquote>
      <div className={`check-card ${sample.status === "failed" ? "status-bad" : "status-idle"}`}>
        <strong>Status: {sample.status}</strong>
        <span>
          {sample.error
            ? sample.error
            : `${completedCount} of ${progress.samples.length} samples completed.`}
        </span>
      </div>
      <p>
        {completedCount} of {progress.samples.length} samples completed.
      </p>
      <div className="actions">
        <button type="button" disabled={running} onClick={() => void runSample()}>
          {running ? "Running sample..." : sample.attempts > 0 ? "Retry sample" : "Start sample"}
        </button>
        <button type="button" disabled={!running} onClick={() => void cancelSample()}>
          Cancel
        </button>
        <button type="button" onClick={() => void goTo("calibrationIntro")}>
          Back
        </button>
      </div>
    </div>
  );
}
