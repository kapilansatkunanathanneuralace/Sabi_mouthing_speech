import type { DesktopSettings } from "../types/sidecar";
import { nextStep } from "./steps";
import type { StepProps } from "./types";

interface Props extends StepProps {
  settings: DesktopSettings;
}

export function CalibrationSummaryStep({ goTo, platform, settings }: Props) {
  const progress = settings.calibrationProgress;
  const passed = progress?.samples.filter((sample) => sample.status === "passed").length ?? 0;
  const total = progress?.samples.length ?? 0;

  return (
    <div className="wizard-step">
      <h2>Calibration summary</h2>
      {progress?.skipped ? (
        <p>Optional calibration was skipped. You can still launch Sabi and calibrate later.</p>
      ) : (
        <p>
          {passed} of {total} optional calibration samples passed. Progress metadata is stored
          locally; raw audio and video are not uploaded.
        </p>
      )}
      <div className="actions">
        {!progress?.skipped && !progress?.completed ? (
          <button type="button" onClick={() => void goTo("calibrationSample")}>
            Continue calibration
          </button>
        ) : null}
        <button type="button" onClick={() => void goTo(nextStep("calibrationSummary", platform))}>
          Continue setup
        </button>
      </div>
    </div>
  );
}
