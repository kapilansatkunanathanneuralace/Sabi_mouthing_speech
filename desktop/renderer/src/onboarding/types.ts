import type { OnboardingStep, PlatformInfo, ProbeResponse, SidecarNotification } from "../types/sidecar";

export type ProbeTarget = "camera" | "microphone";

export interface StepProps {
  goTo: (step: OnboardingStep) => Promise<void>;
  platform: PlatformInfo;
}

export interface ProbeStepProps extends StepProps {
  callProbe: () => Promise<ProbeResponse>;
  openPrivacySettings: (target: ProbeTarget) => Promise<void>;
}

export interface ModelsStepProps extends StepProps {
  callModelDownload: () => Promise<boolean>;
  notifications: SidecarNotification[];
}

export interface DoneStepProps extends StepProps {
  complete: () => Promise<void>;
}
