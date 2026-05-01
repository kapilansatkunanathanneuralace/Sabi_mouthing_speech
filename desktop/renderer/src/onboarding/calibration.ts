import type {
  CalibrationPlanResponse,
  CalibrationProgress,
  CalibrationRunResponse,
  CalibrationSampleProgress
} from "../types/sidecar";

export function emptyCalibrationProgress(): CalibrationProgress {
  return { skipped: false, completed: false, samples: [] };
}

export function progressFromPlan(plan: CalibrationPlanResponse): CalibrationProgress {
  const now = new Date().toISOString();
  return {
    skipped: false,
    completed: false,
    samples: plan.samples.map((sample): CalibrationSampleProgress => ({
      sampleId: sample.sample_id,
      text: sample.text,
      status: "pending",
      attempts: 0,
      updatedAt: now
    }))
  };
}

export function applyCalibrationResult(
  progress: CalibrationProgress,
  result: CalibrationRunResponse
): CalibrationProgress {
  const samples = progress.samples.map((sample) => {
    if (sample.sampleId !== result.sample_id) {
      return sample;
    }
    return {
      ...sample,
      attempts: sample.attempts + 1,
      status: result.ok ? "passed" as const : "failed" as const,
      updatedAt: new Date().toISOString(),
      transcript: result.transcript || undefined,
      error: result.error ?? undefined
    };
  });
  return {
    skipped: false,
    completed: samples.length > 0 && samples.every((sample) => sample.status === "passed"),
    samples
  };
}

export function markCalibrationCancelled(
  progress: CalibrationProgress,
  sampleId: string
): CalibrationProgress {
  return {
    ...progress,
    samples: progress.samples.map((sample) => (
      sample.sampleId === sampleId
        ? {
            ...sample,
            status: "cancelled",
            updatedAt: new Date().toISOString(),
            error: "Calibration attempt cancelled."
          }
        : sample
    ))
  };
}
