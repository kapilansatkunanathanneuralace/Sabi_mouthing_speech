import { useCallback, useEffect, useState } from "react";

import type {
  DesktopSettings,
  DesktopSettingsPatch,
  CalibrationPlanResponse,
  CalibrationRunResponse,
  JsonRpcParams,
  JsonValue,
  OnboardingStep,
  PlatformInfo,
  PrivacySettingsTarget,
  ProbeDevicesResponse,
  ProbeResponse,
  RuntimeStatus,
  SidecarNotification
} from "../types/sidecar";
import { useSupabaseAuth } from "../supabase/useSupabaseAuth";
import { AccessibilityStep } from "./AccessibilityStep";
import { AccountStep } from "./AccountStep";
import { CalibrationIntroStep } from "./CalibrationIntroStep";
import { CalibrationSampleStep } from "./CalibrationSampleStep";
import { CalibrationSummaryStep } from "./CalibrationSummaryStep";
import { DeviceCheckStep } from "./DeviceCheckStep";
import { DoneStep } from "./DoneStep";
import { ModelsStep } from "./ModelsStep";
import { OptionalStep } from "./OptionalStep";
import { OnboardingProgress } from "./OnboardingProgress";
import { PermissionProbeStep } from "./PermissionProbeStep";
import { ProfileIntakeStep } from "./ProfileIntakeStep";
import { ShortcutSetupStep } from "./ShortcutSetupStep";
import { WelcomeStep } from "./WelcomeStep";

interface Props {
  call: (method: string, params?: JsonRpcParams) => Promise<JsonValue>;
  onComplete: (settings: DesktopSettings) => void;
  platform: PlatformInfo;
  runtime: RuntimeStatus | null;
  setRuntime: (runtime: RuntimeStatus) => void;
  settings: DesktopSettings;
}

export function OnboardingWizard({
  call,
  onComplete,
  platform,
  runtime,
  setRuntime,
  settings
}: Props) {
  const [wizardSettings, setWizardSettings] = useState(settings);
  const [step, setStep] = useState<OnboardingStep>(settings.onboardingStep);
  const [notifications, setNotifications] = useState<SidecarNotification[]>([]);
  const { initializing, session } = useSupabaseAuth();
  const visibleStep: OnboardingStep = session?.user ? step : "account";

  useEffect(() => {
    if (!window.sabi) {
      return undefined;
    }
    return window.sabi.sidecar.onNotification((notification) => {
      setNotifications((items) => [...items.slice(-20), notification]);
    });
  }, []);

  const updateSettings = useCallback(async (patch: DesktopSettingsPatch) => {
    const updated = await window.sabi?.settings.update(patch);
    if (updated) {
      setWizardSettings(updated);
    }
    return updated;
  }, []);

  const goTo = useCallback(async (next: OnboardingStep) => {
    setStep(next);
    await updateSettings({ onboardingStep: next });
  }, [updateSettings]);

  useEffect(() => {
    if (initializing || session?.user || step === "account") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      void goTo("account");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [goTo, initializing, session?.user, step]);

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

  async function callDeviceProbe(params: { camera_index?: number; audio_device_index?: number }) {
    const probeParams: Record<string, JsonValue> = {};
    if (params.camera_index !== undefined) {
      probeParams.camera_index = params.camera_index;
    }
    if (params.audio_device_index !== undefined) {
      probeParams.audio_device_index = params.audio_device_index;
    }
    return (await call("probe.run", probeParams)) as unknown as ProbeResponse;
  }

  async function callDevices(): Promise<ProbeDevicesResponse> {
    return (await call("probe.devices", { max_camera_index: 4 })) as unknown as ProbeDevicesResponse;
  }

  async function callModelDownload(): Promise<boolean> {
    const result = (await call("cache.download", { manifests: ["vsr", "asr"] })) as { ok?: boolean };
    return Boolean(result.ok);
  }

  async function callCalibrationPlan(): Promise<CalibrationPlanResponse> {
    return (await call("calibration.plan", { count: 3 })) as unknown as CalibrationPlanResponse;
  }

  async function callCalibrationRun(sample: { sampleId: string; text: string }) {
    return (await call("calibration.run", {
      sample_id: sample.sampleId,
      text: sample.text
    })) as unknown as CalibrationRunResponse;
  }

  async function callCalibrationCancel() {
    await call("calibration.cancel", {});
  }

  async function mediaStatus(target: "camera" | "microphone") {
    return (
      (await window.sabi?.permissions.mediaStatus(target)) ?? {
        supported: false,
        status: "unknown"
      }
    );
  }

  async function requestMediaAccess(target: "camera" | "microphone") {
    return (
      (await window.sabi?.permissions.requestMediaAccess(target)) ?? {
        supported: false,
        granted: true
      }
    );
  }

  async function openPrivacySettings(target: PrivacySettingsTarget) {
    await window.sabi?.platform.openPrivacySettings(target);
  }

  async function validateShortcut(accelerator: string) {
    return (
      (await window.sabi?.shortcuts.validate(accelerator)) ?? {
        ok: false,
        message: "Shortcuts are not available in this environment."
      }
    );
  }

  async function testShortcut(accelerator: string, timeoutMs?: number) {
    return (
      (await window.sabi?.shortcuts.test(accelerator, timeoutMs)) ?? {
        ok: false,
        message: "Shortcuts are not available in this environment."
      }
    );
  }

  return (
    <section className="wizard" aria-label="Onboarding wizard">
      <p className="eyebrow">First launch setup</p>
      <OnboardingProgress step={visibleStep} />
      {visibleStep === "account" ? <AccountStep goTo={goTo} platform={platform} /> : null}
      {visibleStep === "profile" ? (
        <ProfileIntakeStep goTo={goTo} platform={platform} settings={wizardSettings} />
      ) : null}
      {visibleStep === "welcome" ? <WelcomeStep goTo={goTo} platform={platform} /> : null}
      {visibleStep === "camera" ? (
        <PermissionProbeStep
          callProbe={callProbe}
          goTo={goTo}
          mediaStatus={mediaStatus}
          openPrivacySettings={openPrivacySettings}
          platform={platform}
          requestMediaAccess={requestMediaAccess}
          target="camera"
          title="Camera access"
        />
      ) : null}
      {visibleStep === "microphone" ? (
        <PermissionProbeStep
          callProbe={callProbe}
          goTo={goTo}
          mediaStatus={mediaStatus}
          openPrivacySettings={openPrivacySettings}
          platform={platform}
          requestMediaAccess={requestMediaAccess}
          target="microphone"
          title="Microphone access"
        />
      ) : null}
      {visibleStep === "cameraDevice" ? (
        <DeviceCheckStep
          callDevices={callDevices}
          callProbe={callDeviceProbe}
          goTo={goTo}
          platform={platform}
          settings={wizardSettings}
          target="camera"
          updateSettings={updateSettings}
        />
      ) : null}
      {visibleStep === "microphoneDevice" ? (
        <DeviceCheckStep
          callDevices={callDevices}
          callProbe={callDeviceProbe}
          goTo={goTo}
          platform={platform}
          settings={wizardSettings}
          target="microphone"
          updateSettings={updateSettings}
        />
      ) : null}
      {visibleStep === "accessibility" ? (
        <AccessibilityStep
          goTo={goTo}
          openPrivacySettings={openPrivacySettings}
          platform={platform}
        />
      ) : null}
      {visibleStep === "shortcut" ? (
        <ShortcutSetupStep
          goTo={goTo}
          platform={platform}
          settings={wizardSettings}
          testShortcut={testShortcut}
          updateSettings={updateSettings}
          validateShortcut={validateShortcut}
        />
      ) : null}
      {visibleStep === "models" ? (
        <ModelsStep
          callModelDownload={callModelDownload}
          goTo={goTo}
          notifications={notifications}
          platform={platform}
          runtime={runtime}
          setRuntime={setRuntime}
        />
      ) : null}
      {visibleStep === "calibrationIntro" ? (
        <CalibrationIntroStep
          callPlan={callCalibrationPlan}
          goTo={goTo}
          platform={platform}
          settings={wizardSettings}
          updateSettings={updateSettings}
        />
      ) : null}
      {visibleStep === "calibrationSample" ? (
        <CalibrationSampleStep
          callCancel={callCalibrationCancel}
          callRun={callCalibrationRun}
          goTo={goTo}
          platform={platform}
          settings={wizardSettings}
          updateSettings={updateSettings}
        />
      ) : null}
      {visibleStep === "calibrationSummary" ? (
        <CalibrationSummaryStep goTo={goTo} platform={platform} settings={wizardSettings} />
      ) : null}
      {visibleStep === "optional" ? <OptionalStep goTo={goTo} platform={platform} /> : null}
      {visibleStep === "done" ? (
        <DoneStep
          complete={complete}
          goTo={goTo}
          platform={platform}
          settings={wizardSettings}
        />
      ) : null}
    </section>
  );
}
