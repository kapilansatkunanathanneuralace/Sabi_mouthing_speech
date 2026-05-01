import type {
  DesktopSettings,
  OnboardingStep,
  PlatformInfo,
  PrivacySettingsTarget,
  ProbeResponse,
  RuntimeStatus,
  SidecarNotification
} from "../types/sidecar";

export type ProbeTarget = "camera" | "microphone";

export interface StepProps {
  goTo: (step: OnboardingStep) => Promise<void>;
  platform: PlatformInfo;
}

export interface ProbeStepProps extends StepProps {
  callProbe: () => Promise<ProbeResponse>;
  openPrivacySettings: (target: PrivacySettingsTarget) => Promise<void>;
  requestMediaAccess: (target: ProbeTarget) => Promise<{ supported: boolean; granted: boolean }>;
  mediaStatus: (target: ProbeTarget) => Promise<{ supported: boolean; status: string }>;
}

export interface ModelsStepProps extends StepProps {
  callModelDownload: () => Promise<boolean>;
  notifications: SidecarNotification[];
  runtime: RuntimeStatus | null;
  setRuntime: (runtime: RuntimeStatus) => void;
}

export interface DoneStepProps extends StepProps {
  complete: () => Promise<void>;
  settings: DesktopSettings;
}
