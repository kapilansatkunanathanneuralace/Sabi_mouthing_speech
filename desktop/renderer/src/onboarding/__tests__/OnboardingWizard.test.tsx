// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "../OnboardingWizard";
import type { DesktopSettings, PlatformInfo, SidecarNotification } from "../../types/sidecar";

const platform: PlatformInfo = { platform: "win32", isMac: false, isWindows: true };

function settings(step: DesktopSettings["onboardingStep"] = "welcome"): DesktopSettings {
  return {
    mode: "push_to_talk",
    hotkey: "Control+Alt+Space",
    pipeline: "silent",
    pasteOnAccept: true,
    overlayEnabled: false,
    onboardingCompleted: false,
    onboardingStep: step
  };
}

function installBridge(notifications: SidecarNotification[] = []) {
  const callbacks: Array<(notification: SidecarNotification) => void> = [];
  window.sabi = {
    version: vi.fn(),
    sidecar: {
      status: vi.fn(),
      call: vi.fn(),
      reconnect: vi.fn(),
      onStatus: vi.fn(),
      onNotification: (callback) => {
        callbacks.push(callback);
        notifications.forEach(callback);
        return () => undefined;
      }
    },
    logs: { openFolder: vi.fn() },
    cache: { openFolder: vi.fn() },
    settings: {
      get: vi.fn(),
      update: vi.fn(async (patch) => ({ ...settings(), ...patch }))
    },
    platform: {
      info: vi.fn(),
      openPrivacySettings: vi.fn()
    },
    permissions: {
      accessibilityStatus: vi.fn(async () => ({ supported: false, granted: true })),
      mediaStatus: vi.fn()
    }
  };
}

describe("OnboardingWizard", () => {
  beforeEach(() => {
    installBridge();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders welcome and persists moving to camera", async () => {
    render(
      <OnboardingWizard
        call={vi.fn()}
        onComplete={vi.fn()}
        platform={platform}
        settings={settings()}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /start setup/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingStep: "camera" });
    expect(await screen.findByText("Camera access")).toBeTruthy();
  });

  it("gates camera next until probe passes", async () => {
    const call = vi.fn(async () => ({
      probe: {
        runtime: {},
        imports: [],
        torch: {},
        webcam: { ok: true, output: "camera ok" },
        audio: { ok: false, output: "" },
        failures: 0
      }
    }));
    render(<OnboardingWizard call={call} onComplete={vi.fn()} platform={platform} settings={settings("camera")} />);
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /run probe/i }));
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false)
    );
  });

  it("shows model progress and completes download step", async () => {
    installBridge([
      { method: "models.download_vsr.progress", params: { index: 1, total: 2, status: "downloading" } }
    ]);
    const call = vi.fn(async () => ({ ok: true }));
    render(<OnboardingWizard call={call} onComplete={vi.fn()} platform={platform} settings={settings("models")} />);
    expect(screen.getByText("downloading")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /download models/i }));
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false)
    );
  });

  it("completes onboarding from done step", async () => {
    const onComplete = vi.fn();
    render(<OnboardingWizard call={vi.fn()} onComplete={onComplete} platform={platform} settings={settings("done")} />);
    await userEvent.click(screen.getByRole("button", { name: /finish onboarding/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({
      onboardingCompleted: true,
      onboardingStep: "done",
      pipeline: "silent"
    });
    expect(onComplete).toHaveBeenCalled();
  });
});
