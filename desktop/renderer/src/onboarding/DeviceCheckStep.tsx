import { useEffect, useMemo, useState } from "react";

import type {
  DesktopSettings,
  DesktopSettingsPatch,
  OnboardingStep,
  ProbeDevice,
  ProbeDevicesResponse,
  ProbeResponse
} from "../types/sidecar";
import { nextStep } from "./steps";
import { probePassed, probeSummary } from "./probe";
import type { ProbeTarget, StepProps } from "./types";

interface Props extends StepProps {
  callDevices: () => Promise<ProbeDevicesResponse>;
  callProbe: (params: {
    audio_device_index?: number;
    camera_index?: number;
  }) => Promise<ProbeResponse>;
  settings: DesktopSettings;
  target: ProbeTarget;
  updateSettings: (patch: DesktopSettingsPatch) => Promise<DesktopSettings | undefined>;
}

export function DeviceCheckStep({
  callDevices,
  callProbe,
  goTo,
  platform,
  settings,
  target,
  updateSettings
}: Props) {
  const [devices, setDevices] = useState<ProbeDevice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [probing, setProbing] = useState(false);
  const [result, setResult] = useState<ProbeResponse | null>(null);
  const selectedValue = target === "camera"
    ? String(settings.cameraIndex)
    : settings.microphoneDeviceIndex === null
      ? "default"
      : String(settings.microphoneDeviceIndex);
  const passed = result ? probePassed(result, target) : false;
  const availableDevices = useMemo(
    () => devices.filter(
      (device) => device.available || device.index === selectedIndex(selectedValue)
    ),
    [devices, selectedValue]
  );

  useEffect(() => {
    let cancelled = false;
    void callDevices()
      .then((response) => {
        if (cancelled) {
          return;
        }
        setDevices(target === "camera" ? response.cameras : response.microphones);
      })
      .catch((deviceError) => {
        if (!cancelled) {
          setError(deviceError instanceof Error ? deviceError.message : String(deviceError));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [callDevices, target]);

  async function updateSelection(value: string) {
    setResult(null);
    if (target === "camera") {
      await updateSettings({ cameraIndex: Number(value) });
      return;
    }
    await updateSettings({
      microphoneDeviceIndex: value === "default" ? null : Number(value)
    });
  }

  async function runProbe() {
    setProbing(true);
    setError(null);
    try {
      const probeResult = await callProbe(
        target === "camera"
          ? { camera_index: settings.cameraIndex }
          : {
              camera_index: settings.cameraIndex,
              audio_device_index: settings.microphoneDeviceIndex ?? undefined
            }
      );
      setResult(probeResult);
      if (!probePassed(probeResult, target)) {
        setError(`${label} probe failed. Choose another device or retry.`);
      }
    } catch (probeError) {
      setError(probeError instanceof Error ? probeError.message : String(probeError));
    } finally {
      setProbing(false);
    }
  }

  const label = target === "camera" ? "Camera" : "Microphone";
  const currentStep: OnboardingStep = target === "camera" ? "cameraDevice" : "microphoneDevice";

  return (
    <div className="wizard-step">
      <h2>{label} device check</h2>
      <p>
        Choose the {target} Sabi should use, then run a device-specific probe before continuing.
      </p>
      <label>
        {label}
        <select
          disabled={loading || probing}
          onChange={(event) => void updateSelection(event.target.value)}
          value={selectedValue}
        >
          {target === "microphone" ? <option value="default">System default microphone</option> : null}
          {availableDevices.map((device) => (
            <option key={`${device.kind}-${device.index}`} value={device.index}>
              {device.name} {device.available ? "" : "(unavailable)"}
            </option>
          ))}
        </select>
      </label>
      {loading ? <p>Loading devices...</p> : null}
      {result ? (
        <div className={`check-card ${passed ? "status-good" : "status-bad"}`}>
          <strong>{passed ? `${label} probe passed` : `${label} probe failed`}</strong>
          <span>{probeSummary(result, target)}</span>
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button type="button" disabled={loading || probing} onClick={() => void runProbe()}>
          {probing ? "Running probe..." : result ? "Retry probe" : `Probe ${target}`}
        </button>
        <button
          type="button"
          disabled={!passed}
          onClick={() => void goTo(nextStep(currentStep, platform))}
        >
          Continue
        </button>
      </div>
    </div>
  );
}

function selectedIndex(value: string): number {
  return value === "default" ? -1 : Number(value);
}
