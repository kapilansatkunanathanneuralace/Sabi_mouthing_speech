// @vitest-environment jsdom

import * as React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizard } from "../OnboardingWizard";
import type {
  DesktopSettings,
  PlatformInfo,
  RuntimeStatus,
  SidecarNotification
} from "../../types/sidecar";

const platform: PlatformInfo = { platform: "win32", isMac: false, isWindows: true };
const installedRuntime: RuntimeStatus = {
  state: "installed",
  root: "C:/Users/example/AppData/Local/Sabi/runtime/full-cpu",
  active_dir: "C:/Users/example/AppData/Local/Sabi/runtime/full-cpu/current",
  sidecar_bin: "C:/Users/example/AppData/Local/Sabi/runtime/full-cpu/current/sabi-sidecar/sabi-sidecar.exe",
  manifest: {
    name: "sabi-full-cpu-runtime",
    version: "0.0.1",
    platform: "win32",
    arch: "x64",
    min_desktop_version: "0.0.1",
    url: "",
    sha256: "",
    size_bytes: 0,
    artifact: "runtime.zip",
    sidecar_dir: "sabi-sidecar",
    description: "Full CPU runtime"
  }
};

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
    clipboard: { writeText: vi.fn() },
    dictationHistory: {
      load: vi.fn(async () => []),
      save: vi.fn(),
      clear: vi.fn()
    },
    cache: { openFolder: vi.fn() },
    runtime: {
      status: vi.fn(),
      download: vi.fn(),
      verify: vi.fn(),
      activate: vi.fn(),
      clear: vi.fn()
    },
    ollama: {
      status: vi.fn(async () => ({
        cliFound: false,
        apiReachable: false,
        baseUrl: "http://127.0.0.1:11434",
        model: "llama3.2:3b-instruct-q4_K_M",
        modelPresent: false,
        installed: false,
        ready: false,
        detail: "Ollama is not installed or is not on PATH.",
        models: []
      })),
      openInstaller: vi.fn(),
      pullModel: vi.fn(),
      onProgress: vi.fn(() => () => undefined)
    },
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
      React.createElement(OnboardingWizard, {
        call: vi.fn(),
        onComplete: vi.fn(),
        platform,
        runtime: null,
        setRuntime: vi.fn(),
        settings: settings()
      })
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
    render(
      React.createElement(OnboardingWizard, {
        call,
        onComplete: vi.fn(),
        platform,
        runtime: null,
        setRuntime: vi.fn(),
        settings: settings("camera")
      })
    );
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
    render(
      React.createElement(OnboardingWizard, {
        call,
        onComplete: vi.fn(),
        platform,
        runtime: installedRuntime,
        setRuntime: vi.fn(),
        settings: settings("models")
      })
    );
    expect(screen.getByText("downloading")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /download models/i }));
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false)
    );
  });

  it("completes onboarding from done step", async () => {
    const onComplete = vi.fn();
    render(
      React.createElement(OnboardingWizard, {
        call: vi.fn(),
        onComplete,
        platform,
        runtime: null,
        setRuntime: vi.fn(),
        settings: settings("done")
      })
    );
    await userEvent.click(screen.getByRole("button", { name: /finish onboarding/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({
      onboardingCompleted: true,
      onboardingStep: "done",
      pipeline: "silent"
    });
    expect(onComplete).toHaveBeenCalled();
  });
});
