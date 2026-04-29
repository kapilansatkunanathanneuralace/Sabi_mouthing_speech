import type { OnboardingStep, PlatformInfo } from "../types/sidecar";

export const allOnboardingSteps: OnboardingStep[] = [
  "welcome",
  "camera",
  "microphone",
  "accessibility",
  "models",
  "optional",
  "done"
];

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
