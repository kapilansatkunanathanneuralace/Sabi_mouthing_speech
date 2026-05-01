import type {
  CalibrationPlanResponse,
  DesktopSettings,
  DesktopSettingsPatch
} from "../types/sidecar";
import { nextStep } from "./steps";
import { progressFromPlan } from "./calibration";
import type { StepProps } from "./types";

interface Props extends StepProps {
  callPlan: () => Promise<CalibrationPlanResponse>;
  settings: DesktopSettings;
  updateSettings: (patch: DesktopSettingsPatch) => Promise<DesktopSettings | undefined>;
}

export function CalibrationIntroStep({
  callPlan,
  goTo,
  platform,
  settings,
  updateSettings
}: Props) {
  async function startCalibration() {
    const progress = settings.calibrationProgress?.samples.length
      ? settings.calibrationProgress
      : progressFromPlan(await callPlan());
    await updateSettings({ calibrationProgress: progress });
    await goTo("calibrationSample");
  }

  async function skipCalibration() {
    await updateSettings({
      calibrationProgress: {
        skipped: true,
        completed: false,
        samples: settings.calibrationProgress?.samples ?? []
      }
    });
    await goTo(nextStep("calibrationSummary", platform));
  }

  return (
    <div className="wizard-step">
      <h2>Optional calibration</h2>
      <p>
        Sabi can run three short sentence samples to check how your selected camera and microphone
        perform with your face, voice, and room.
      </p>
      <p>
        Calibration is optional. Progress metadata stays local in desktop settings. Raw audio and
        video are not uploaded, and this does not fine-tune a model.
      </p>
      <div className="actions">
        <button type="button" onClick={() => void startCalibration()}>
          Start optional calibration
        </button>
        <button type="button" onClick={() => void skipCalibration()}>
          Skip calibration
        </button>
      </div>
    </div>
  );
}
