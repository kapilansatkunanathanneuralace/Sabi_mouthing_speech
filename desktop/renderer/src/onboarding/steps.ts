import type { OnboardingStep, PlatformInfo } from "../types/sidecar";

export type OnboardingPhaseId = "phase1" | "phase2" | "phase3" | "launch";

export interface OnboardingPhase {
  id: OnboardingPhaseId;
  label: string;
  steps: OnboardingStep[];
}

export const allOnboardingSteps: OnboardingStep[] = [
  "account",
  "profile",
  "welcome",
  "camera",
  "cameraDevice",
  "microphone",
  "microphoneDevice",
  "accessibility",
  "shortcut",
  "models",
  "calibrationIntro",
  "calibrationSample",
  "calibrationSummary",
  "optional",
  "done"
];

export const onboardingPhases: OnboardingPhase[] = [
  {
    id: "phase1",
    label: "Phase 1: Account and profile",
    steps: ["account", "profile", "welcome"]
  },
  {
    id: "phase2",
    label: "Phase 2: Permissions and setup",
    steps: [
      "camera",
      "cameraDevice",
      "microphone",
      "microphoneDevice",
      "accessibility",
      "shortcut",
      "models"
    ]
  },
  {
    id: "phase3",
    label: "Phase 3: Optional calibration",
    steps: ["calibrationIntro", "calibrationSample", "calibrationSummary"]
  },
  {
    id: "launch",
    label: "Launch",
    steps: ["optional", "done"]
  }
];

export const substepLabels: Record<OnboardingStep, string> = {
  account: "Sign in or create account",
  profile: "Profile intake",
  welcome: "Welcome",
  camera: "Camera permission",
  cameraDevice: "Camera device check",
  microphone: "Microphone permission",
  microphoneDevice: "Microphone device check",
  accessibility: "Text, paste, and input permissions",
  shortcut: "Shortcut setup",
  models: "Model download",
  calibrationIntro: "Calibration choice",
  calibrationSample: "Calibration samples",
  calibrationSummary: "Calibration summary",
  optional: "Optional tools",
  done: "Launch Sabi"
};

export function stepsForPlatform(platform: PlatformInfo): OnboardingStep[] {
  if (platform.isMac) {
    return allOnboardingSteps;
  }
  return allOnboardingSteps;
}

export function nextStep(current: OnboardingStep, platform: PlatformInfo): OnboardingStep {
  const steps = stepsForPlatform(platform);
  const index = steps.indexOf(current);
  return steps[Math.min(index + 1, steps.length - 1)] ?? "done";
}

export function phaseForStep(step: OnboardingStep): OnboardingPhase {
  return onboardingPhases.find((phase) => phase.steps.includes(step)) ?? onboardingPhases[0];
}

export function substepLabel(step: OnboardingStep): string {
  return substepLabels[step];
}

export function phaseProgress(step: OnboardingStep) {
  const phase = phaseForStep(step);
  const phaseIndex = onboardingPhases.findIndex((item) => item.id === phase.id);
  const substepIndex = phase.steps.indexOf(step);
  return {
    phase,
    phaseIndex,
    phaseNumber: phaseIndex + 1,
    phaseTotal: onboardingPhases.length,
    substepIndex,
    substepNumber: substepIndex + 1,
    substepTotal: phase.steps.length,
    substepLabel: substepLabel(step)
  };
}
