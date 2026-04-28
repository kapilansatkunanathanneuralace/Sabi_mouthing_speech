import { useEffect, useMemo, useState } from "react";

import type {
  DesktopSettings,
  JsonRpcParams,
  JsonValue,
  OnboardingStep,
  PlatformInfo,
  ProbeResponse,
  SidecarNotification
} from "../types/sidecar";
import { AccessibilityStep } from "./AccessibilityStep";
import { DoneStep } from "./DoneStep";
import { ModelsStep } from "./ModelsStep";
import { OptionalStep } from "./OptionalStep";
import { PermissionProbeStep } from "./PermissionProbeStep";
import { stepsForPlatform } from "./steps";
import { WelcomeStep } from "./WelcomeStep";

interface Props {
  call: (method: string, params?: JsonRpcParams) => Promise<JsonValue>;
  onComplete: (settings: DesktopSettings) => void;
  platform: PlatformInfo;
  settings: DesktopSettings;
}

export function OnboardingWizard({ call, onComplete, platform, settings }: Props) {
  const [step, setStep] = useState<OnboardingStep>(settings.onboardingStep);
  const [notifications, setNotifications] = useState<SidecarNotification[]>([]);
  const steps = useMemo(() => stepsForPlatform(platform), [platform]);

  useEffect(() => {
    if (!window.sabi) {
      return undefined;
    }
    return window.sabi.sidecar.onNotification((notification) => {
      setNotifications((items) => [...items.slice(-20), notification]);
    });
  }, []);

  async function goTo(next: OnboardingStep) {
    setStep(next);
    await window.sabi?.settings.update({ onboardingStep: next });
  }

  async function complete() {
    const next = await window.sabi?.settings.update({
      onboardingCompleted: true,
      onboardingStep: "done",
      pipeline: "silent"
    });
    if (next) {
      onComplete(next);
    }
  }

  async function callProbe(): Promise<ProbeResponse> {
    return (await call("probe.run", { camera_index: 0 })) as unknown as ProbeResponse;
  }

  async function callModelDownload(): Promise<boolean> {
    const result = (await call("cache.download", { manifests: ["vsr", "asr"] })) as { ok?: boolean };
    return Boolean(result.ok);
  }

  async function openPrivacySettings(target: "camera" | "microphone") {
    await window.sabi?.platform.openPrivacySettings(target);
  }

  return (
    <section className="wizard" aria-label="Onboarding wizard">
      <p className="eyebrow">First launch setup</p>
      <div className="wizard-progress">
        {steps.map((item) => (
          <span key={item} className={item === step ? "active" : ""}>
            {item}
          </span>
        ))}
      </div>
      {step === "welcome" ? <WelcomeStep goTo={goTo} platform={platform} /> : null}
      {step === "camera" ? (
        <PermissionProbeStep
          callProbe={callProbe}
          goTo={goTo}
          openPrivacySettings={openPrivacySettings}
          platform={platform}
          target="camera"
          title="Camera access"
        />
      ) : null}
      {step === "microphone" ? (
        <PermissionProbeStep
          callProbe={callProbe}
          goTo={goTo}
          openPrivacySettings={openPrivacySettings}
          platform={platform}
          target="microphone"
          title="Microphone access"
        />
      ) : null}
      {step === "accessibility" ? <AccessibilityStep goTo={goTo} platform={platform} /> : null}
      {step === "models" ? (
        <ModelsStep
          callModelDownload={callModelDownload}
          goTo={goTo}
          notifications={notifications}
          platform={platform}
        />
      ) : null}
      {step === "optional" ? <OptionalStep goTo={goTo} platform={platform} /> : null}
      {step === "done" ? <DoneStep complete={complete} goTo={goTo} platform={platform} /> : null}
    </section>
  );
}
