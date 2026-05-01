// @vitest-environment jsdom

import * as React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const supabaseMocks = vi.hoisted(() => {
  const upsert = vi.fn();
  const from = vi.fn(() => ({ upsert }));
  return { from, upsert };
});

vi.mock("../../supabaseClient", () => ({
  getSupabase: () => ({ from: supabaseMocks.from }),
  isSupabaseConfigured: () => true
}));

import { OnboardingWizard } from "../OnboardingWizard";
import {
  SupabaseAuthContext,
  type SupabaseAuthContextValue
} from "../../supabase/SupabaseAuthContext";
import type {
  CalibrationProgress,
  DesktopSettings,
  JsonValue,
  PlatformInfo,
  RuntimeStatus,
  OnboardingProfileDraft,
  SidecarNotification
} from "../../types/sidecar";

const platform: PlatformInfo = { platform: "win32", isMac: false, isWindows: true };
const macPlatform: PlatformInfo = { platform: "darwin", isMac: true, isWindows: false };
const signedInSession = {
  user: {
    id: "user-1",
    email: "user@example.com"
  }
} as unknown as SupabaseAuthContextValue["session"];
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

function settings(
  step: DesktopSettings["onboardingStep"] = "account",
  onboardingProfileDraft: OnboardingProfileDraft | null = null,
  calibrationProgress: CalibrationProgress | null = null
): DesktopSettings {
  return {
    mode: "push_to_talk",
    hotkey: "Control+Alt+Space",
    pipeline: "silent",
    pasteOnAccept: true,
    overlayEnabled: false,
    onboardingCompleted: false,
    onboardingStep: step,
    onboardingProfileDraft,
    cameraIndex: 0,
    microphoneDeviceIndex: null,
    shortcutVerified: false,
    calibrationProgress
  };
}

function auth(overrides: Partial<SupabaseAuthContextValue> = {}): SupabaseAuthContextValue {
  return {
    configured: true,
    initializing: false,
    session: null,
    signUp: vi.fn(async () => ({ errorMessage: null, confirmationHint: false })),
    signIn: vi.fn(async () => ({ errorMessage: null })),
    signOut: vi.fn(async () => ({ errorMessage: null })),
    ...overrides
  };
}

function renderWizard({
  authValue = auth({ session: signedInSession }),
  call = vi.fn(),
  onComplete = vi.fn(),
  runtime = null,
  setRuntime = vi.fn(),
  profileDraft = null,
  calibrationProgress = null,
  testPlatform = platform,
  step = "account"
}: {
  authValue?: SupabaseAuthContextValue;
  call?: Parameters<typeof OnboardingWizard>[0]["call"];
  onComplete?: Parameters<typeof OnboardingWizard>[0]["onComplete"];
  profileDraft?: OnboardingProfileDraft | null;
  calibrationProgress?: CalibrationProgress | null;
  runtime?: RuntimeStatus | null;
  setRuntime?: Parameters<typeof OnboardingWizard>[0]["setRuntime"];
  testPlatform?: PlatformInfo;
  step?: DesktopSettings["onboardingStep"];
} = {}) {
  return render(
    React.createElement(
      SupabaseAuthContext.Provider,
      { value: authValue },
      React.createElement(OnboardingWizard, {
        call,
        onComplete,
        platform: testPlatform,
        runtime,
        setRuntime,
        settings: settings(step, profileDraft, calibrationProgress)
      })
    )
  );
}

function installBridge(notifications: SidecarNotification[] = []) {
  const callbacks: Array<(notification: SidecarNotification) => void> = [];
  let bridgeSettings = settings();
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
      update: vi.fn(async (patch) => {
        bridgeSettings = { ...bridgeSettings, ...patch };
        return bridgeSettings;
      })
    },
    platform: {
      info: vi.fn(),
      openPrivacySettings: vi.fn()
    },
    permissions: {
      accessibilityStatus: vi.fn(async () => ({ supported: false, granted: true })),
      mediaStatus: vi.fn(async () => ({ supported: false, status: "unknown" })),
      requestMediaAccess: vi.fn(async () => ({ supported: false, granted: true }))
    },
    shortcuts: {
      validate: vi.fn(async () => ({ ok: true, message: "Shortcut is available." })),
      test: vi.fn(async () => ({ ok: true, message: "Shortcut received." }))
    }
  };
}

describe("OnboardingWizard", () => {
  beforeEach(() => {
    installBridge();
    supabaseMocks.from.mockClear();
    supabaseMocks.upsert.mockReset();
    supabaseMocks.upsert.mockResolvedValue({ error: null });
  });

  afterEach(() => {
    cleanup();
  });

  it("starts on the account step for fresh onboarding", () => {
    renderWizard({ authValue: auth(), step: "account" });
    expect(screen.getByText("Create your Sabi account")).toBeTruthy();
    expect(screen.queryByText("Camera access")).toBeNull();
  });

  it("shows phase progress instead of internal step pills", () => {
    renderWizard({ step: "cameraDevice" });
    expect(screen.getByText("Phase 2: Permissions and setup")).toBeTruthy();
    expect(screen.getByText(/Step 2 of 7: Camera device check/)).toBeTruthy();
    expect(screen.queryByText("cameraDevice")).toBeNull();
  });

  it("shows missing Supabase configuration as a blocking account state", () => {
    renderWizard({ authValue: auth({ configured: false }), step: "account" });
    expect(screen.getByText(/VITE_SUPABASE_URL/)).toBeTruthy();
    expect(screen.getByText(/VITE_SUPABASE_PUBLISHABLE_KEY/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /continue/i })).toBeNull();
  });

  it("continues from account to profile once signed in", async () => {
    renderWizard({ step: "account" });
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingStep: "profile" });
    expect(await screen.findByText("Tell us how you will use Sabi")).toBeTruthy();
  });

  it("redirects signed-out users back to account from later persisted steps", async () => {
    renderWizard({ authValue: auth(), step: "camera" });
    expect(screen.getByText("Create your Sabi account")).toBeTruthy();
    await waitFor(() =>
      expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingStep: "account" })
    );
  });

  it("calls sign in from the account form", async () => {
    const authValue = auth();
    renderWizard({ authValue, step: "account" });
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "password1");
    const signInButtons = screen.getAllByRole("button", { name: /^sign in$/i });
    await userEvent.click(signInButtons[signInButtons.length - 1]);
    await waitFor(() => expect(authValue.signIn).toHaveBeenCalledWith("user@example.com", "password1"));
  });

  it("blocks profile progression until required fields are complete", async () => {
    renderWizard({ step: "profile" });
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(screen.getByText("Choose how you heard about Sabi.")).toBeTruthy();
    expect(supabaseMocks.upsert).not.toHaveBeenCalled();
  });

  it("persists profile draft changes locally", async () => {
    renderWizard({ step: "profile" });
    await userEvent.selectOptions(screen.getByLabelText(/how did you hear/i), "search");
    await waitFor(() =>
      expect(window.sabi?.settings.update).toHaveBeenCalledWith(
        expect.objectContaining({
          onboardingProfileDraft: expect.objectContaining({ referralSource: "search" })
        })
      )
    );
  });

  it("loads a saved profile draft", () => {
    renderWizard({
      profileDraft: {
        referralSource: "social",
        profession: "Designer",
        useCases: ["meetings"],
        workEnvironment: "office",
        updatedAt: "2026-05-01T00:00:00.000Z"
      },
      step: "profile"
    });
    expect((screen.getByLabelText(/profession/i) as HTMLInputElement).value).toBe("Designer");
    expect((screen.getByLabelText(/meetings/i) as HTMLInputElement).checked).toBe(true);
  });

  it("syncs profile intake and advances to welcome", async () => {
    renderWizard({ step: "profile" });
    await userEvent.selectOptions(screen.getByLabelText(/how did you hear/i), "friend");
    await userEvent.type(screen.getByLabelText(/profession/i), "Engineer");
    await userEvent.click(screen.getByLabelText(/silent dictation/i));
    await userEvent.selectOptions(screen.getByLabelText(/work environment/i), "home");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() =>
      expect(supabaseMocks.upsert).toHaveBeenCalledWith(
        {
          user_id: "user-1",
          referral_source: "friend",
          profession: "Engineer",
          use_cases: ["silent_dictation"],
          work_environment: "home"
        },
        { onConflict: "user_id" }
      )
    );
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingProfileDraft: null });
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingStep: "welcome" });
  });

  it("shows profile sync failure without clearing form values", async () => {
    supabaseMocks.upsert.mockResolvedValue({ error: { message: "RLS denied" } });
    renderWizard({ step: "profile" });
    await userEvent.selectOptions(screen.getByLabelText(/how did you hear/i), "community");
    await userEvent.type(screen.getByLabelText(/profession/i), "Researcher");
    await userEvent.click(screen.getByLabelText(/experimentation/i));
    await userEvent.selectOptions(screen.getByLabelText(/work environment/i), "hybrid");
    await userEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(await screen.findByText("Profile sync failed: RLS denied")).toBeTruthy();
    expect((screen.getByLabelText(/profession/i) as HTMLInputElement).value).toBe("Researcher");
    expect((screen.getByLabelText(/experimentation/i) as HTMLInputElement).checked).toBe(true);
  });

  it("renders welcome and persists moving to camera", async () => {
    renderWizard({ step: "welcome" });
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
    renderWizard({ call, step: "camera" });
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /request \/ check access/i }));
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false)
    );
  });

  it("shows camera probe failure with retry and settings actions", async () => {
    const call = vi.fn(async () => ({
      probe: {
        runtime: {},
        imports: [],
        torch: {},
        webcam: { ok: false, output: "camera missing" },
        audio: { ok: false, output: "" },
        failures: 1
      }
    }));
    renderWizard({ call, step: "camera" });
    await userEvent.click(screen.getByRole("button", { name: /request \/ check access/i }));
    expect(await screen.findByText(/Hardware check failed/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry check/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /open windows privacy settings/i })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows macOS media denial before running probe", async () => {
    window.sabi!.permissions.mediaStatus = vi.fn(async () => ({
      supported: true,
      status: "denied"
    }));
    const call = vi.fn();
    renderWizard({ call, step: "camera", testPlatform: macPlatform });
    await userEvent.click(screen.getByRole("button", { name: /request \/ check access/i }));
    expect(await screen.findByText(/OS permission is denied/i)).toBeTruthy();
    expect(call).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /open system settings/i })).toBeTruthy();
  });

  it("runs probe after macOS media permission is granted", async () => {
    window.sabi!.permissions.mediaStatus = vi.fn(async () => ({
      supported: true,
      status: "granted"
    }));
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
    renderWizard({ call, step: "camera", testPlatform: macPlatform });
    await userEvent.click(screen.getByRole("button", { name: /request \/ check access/i }));
    await waitFor(() => expect(call).toHaveBeenCalled());
    expect(await screen.findByText("OS permission is granted.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("loads camera devices, persists selection, and probes selected camera", async () => {
    const call: Parameters<typeof OnboardingWizard>[0]["call"] = vi.fn(async (method, params) => {
      if (method === "probe.devices") {
        return {
          cameras: [
            { kind: "camera", index: 0, name: "Built-in Camera", available: true },
            { kind: "camera", index: 2, name: "USB Camera", available: true }
          ],
          microphones: []
        } as JsonValue;
      }
      expect(params).toEqual({ camera_index: 2 });
      return {
        probe: {
          runtime: {},
          imports: [],
          torch: {},
          webcam: { ok: true, output: "usb camera ok" },
          audio: { ok: false, output: "" },
          failures: 0
        }
      } as JsonValue;
    });
    renderWizard({ call, step: "cameraDevice" });
    await screen.findByText("USB Camera");
    await userEvent.selectOptions(screen.getByLabelText(/^camera$/i), "2");
    await waitFor(() => expect(window.sabi?.settings.update).toHaveBeenCalledWith(
      expect.objectContaining({ cameraIndex: 2 })
    ));
    await userEvent.click(screen.getByRole("button", { name: /probe camera/i }));
    expect(await screen.findByText("Camera probe passed")).toBeTruthy();
  });

  it("persists microphone selection and probes selected audio device", async () => {
    const call: Parameters<typeof OnboardingWizard>[0]["call"] = vi.fn(async (method, params) => {
      if (method === "probe.devices") {
        return {
          cameras: [],
          microphones: [
            { kind: "microphone", index: 5, name: "Headset Mic", available: true }
          ]
        } as JsonValue;
      }
      expect(params).toEqual({ camera_index: 0, audio_device_index: 5 });
      return {
        probe: {
          runtime: {},
          imports: [],
          torch: {},
          webcam: { ok: false, output: "" },
          audio: { ok: true, output: "headset ok" },
          failures: 0
        }
      } as JsonValue;
    });
    renderWizard({ call, step: "microphoneDevice" });
    await screen.findByText("Headset Mic");
    await userEvent.selectOptions(screen.getByLabelText(/^microphone$/i), "5");
    await waitFor(() => expect(window.sabi?.settings.update).toHaveBeenCalledWith(
      expect.objectContaining({ microphoneDeviceIndex: 5 })
    ));
    await userEvent.click(screen.getByRole("button", { name: /probe microphone/i }));
    expect(await screen.findByText("Microphone probe passed")).toBeTruthy();
  });

  it("shows device probe failure with retry/change path", async () => {
    const call: Parameters<typeof OnboardingWizard>[0]["call"] = vi.fn(async (method) => {
      if (method === "probe.devices") {
        return {
          cameras: [{ kind: "camera", index: 0, name: "Built-in Camera", available: true }],
          microphones: []
        } as JsonValue;
      }
      return {
        probe: {
          runtime: {},
          imports: [],
          torch: {},
          webcam: { ok: false, output: "camera blocked" },
          audio: { ok: false, output: "" },
          failures: 1
        }
      } as JsonValue;
    });
    renderWizard({ call, step: "cameraDevice" });
    await screen.findByText("Built-in Camera");
    await userEvent.click(screen.getByRole("button", { name: /probe camera/i }));
    expect(await screen.findAllByText(/Camera probe failed/)).toHaveLength(2);
    expect(screen.getByRole("button", { name: /retry probe/i })).toBeTruthy();
    expect((screen.getByRole("button", { name: /continue/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows shortcut validation conflicts", async () => {
    window.sabi!.shortcuts.validate = vi.fn(async () => ({
      ok: false,
      message: "Shortcut could not be registered. It may be in use."
    }));
    renderWizard({ step: "shortcut" });
    await userEvent.clear(screen.getByLabelText(/shortcut/i));
    await userEvent.type(screen.getByLabelText(/shortcut/i), "Control+Shift+Space");
    await userEvent.click(screen.getByRole("button", { name: /validate shortcut/i }));
    expect(await screen.findByText(/may be in use/i)).toBeTruthy();
    expect(window.sabi?.settings.update).not.toHaveBeenCalledWith(
      expect.objectContaining({ hotkey: "Control+Shift+Space" })
    );
  });

  it("requires shortcut press confirmation before continuing", async () => {
    renderWizard({ step: "shortcut" });
    expect((screen.getByRole("button", { name: /continue/i }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /validate shortcut/i }));
    await userEvent.click(screen.getByRole("button", { name: /press to confirm/i }));
    await waitFor(() => expect(window.sabi?.settings.update).toHaveBeenCalledWith(
      expect.objectContaining({ shortcutVerified: true })
    ));
    expect((screen.getByRole("button", { name: /continue/i }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("gates macOS text and input permissions until accessibility is granted", async () => {
    window.sabi!.permissions.accessibilityStatus = vi.fn(async () => ({
      supported: true,
      granted: false
    }));
    renderWizard({ step: "accessibility", testPlatform: macPlatform });
    expect((screen.getByRole("button", { name: /continue/i }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /check permission/i }));
    expect(await screen.findByText(/Accessibility permission is not granted yet/i)).toBeTruthy();
    expect((screen.getByRole("button", { name: /continue/i }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("button", { name: /open accessibility settings/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /open input monitoring settings/i })).toBeTruthy();
  });

  it("allows Windows text and input permission step to continue", async () => {
    renderWizard({ step: "accessibility" });
    expect(
      screen.getByText(/Windows does not require a separate Accessibility permission/i)
    ).toBeTruthy();
    expect((screen.getByRole("button", { name: /continue/i }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows model progress and completes download step", async () => {
    installBridge([
      { method: "models.download_vsr.progress", params: { index: 1, total: 2, status: "downloading" } }
    ]);
    const call = vi.fn(async () => ({ ok: true }));
    renderWizard({ call, runtime: installedRuntime, step: "models" });
    expect(screen.getByText("downloading")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /download models/i }));
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false)
    );
  });

  it("routes from models to optional calibration", async () => {
    const call = vi.fn(async () => ({ ok: true }));
    renderWizard({ call, runtime: installedRuntime, step: "models" });
    await userEvent.click(screen.getByRole("button", { name: /download models/i }));
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(false)
    );
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Optional calibration")).toBeTruthy();
  });

  it("allows users to skip optional calibration", async () => {
    renderWizard({ step: "calibrationIntro" });
    await userEvent.click(screen.getByRole("button", { name: /skip calibration/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({
      calibrationProgress: { skipped: true, completed: false, samples: [] }
    });
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingStep: "optional" });
  });

  it("resumes from a calibration phase with progress labels", () => {
    renderWizard({
      calibrationProgress: {
        skipped: false,
        completed: false,
        samples: [
          {
            sampleId: "one",
            text: "One bright sentence.",
            status: "pending",
            attempts: 0,
            updatedAt: "2026-05-01T00:00:00.000Z"
          }
        ]
      },
      step: "calibrationSample"
    });
    expect(screen.getByText("Phase 3: Optional calibration")).toBeTruthy();
    expect(screen.getByText(/Step 2 of 3: Calibration samples/)).toBeTruthy();
    expect(screen.getByText("One bright sentence.")).toBeTruthy();
  });

  it("plans random calibration samples and runs them to summary", async () => {
    const call = vi.fn(async (method, params) => {
      if (method === "calibration.plan") {
        expect(params).toEqual({ count: 3 });
        return {
          samples: [
            { sample_id: "one", text: "One bright sentence.", index: 1, total: 3, mode: "optional" },
            { sample_id: "two", text: "Two calm words.", index: 2, total: 3, mode: "optional" },
            { sample_id: "three", text: "Three sample sounds.", index: 3, total: 3, mode: "optional" }
          ]
        } as JsonValue;
      }
      return {
        sample_id: (params as Record<string, JsonValue>).sample_id,
        text: (params as Record<string, JsonValue>).text,
        mode: "optional",
        ok: true,
        status: "passed",
        transcript: (params as Record<string, JsonValue>).text,
        error: null,
        quality: { non_empty_output: true }
      } as JsonValue;
    });
    renderWizard({ call, step: "calibrationIntro" });

    await userEvent.click(screen.getByRole("button", { name: /start optional calibration/i }));
    expect(await screen.findByText("One bright sentence.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /start sample/i }));
    expect(await screen.findByText("Two calm words.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /start sample/i }));
    expect(await screen.findByText("Three sample sounds.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /start sample/i }));

    expect(await screen.findByText("Calibration summary")).toBeTruthy();
    expect(screen.getByText(/3 of 3 optional calibration samples passed/i)).toBeTruthy();
  });

  it("shows calibration failure and allows retry without losing prior samples", async () => {
    const progress: CalibrationProgress = {
      skipped: false,
      completed: false,
      samples: [
        {
          sampleId: "one",
          text: "One bright sentence.",
          status: "passed",
          attempts: 1,
          updatedAt: "2026-05-01T00:00:00.000Z"
        },
        {
          sampleId: "two",
          text: "Two calm words.",
          status: "pending",
          attempts: 0,
          updatedAt: "2026-05-01T00:00:00.000Z"
        }
      ]
    };
    const call = vi.fn(async () => ({
      sample_id: "two",
      text: "Two calm words.",
      mode: "optional",
      ok: false,
      status: "failed",
      transcript: "",
      error: "calibration sample failed quality checks",
      quality: { non_empty_output: false }
    }));
    renderWizard({ call, calibrationProgress: progress, step: "calibrationSample" });

    expect(screen.getByText("Two calm words.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /start sample/i }));
    expect(await screen.findByText(/calibration sample failed quality checks/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry sample/i })).toBeTruthy();
    expect(screen.getByText(/1 of 2 samples completed/i)).toBeTruthy();
  });

  it("cancels a calibration sample and persists cancelled status", async () => {
    const progress: CalibrationProgress = {
      skipped: false,
      completed: false,
      samples: [
        {
          sampleId: "one",
          text: "One bright sentence.",
          status: "pending",
          attempts: 0,
          updatedAt: "2026-05-01T00:00:00.000Z"
        }
      ]
    };
    let resolveRun: (value: JsonValue) => void = () => undefined;
    const call = vi.fn(async (method) => {
      if (method === "calibration.cancel") {
        return { cancelled: true, sample_id: "one" };
      }
      return new Promise<JsonValue>((resolve) => {
        resolveRun = resolve;
      });
    });
    renderWizard({ call, calibrationProgress: progress, step: "calibrationSample" });

    await userEvent.click(screen.getByRole("button", { name: /start sample/i }));
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({
      calibrationProgress: expect.objectContaining({
        samples: [
          expect.objectContaining({
            sampleId: "one",
            status: "cancelled"
          })
        ]
      })
    });
    resolveRun({
      sample_id: "one",
      text: "One bright sentence.",
      mode: "optional",
      ok: false,
      status: "cancelled",
      transcript: "",
      error: "cancelled",
      quality: {}
    });
  });

  it("moves from calibration summary to launch", async () => {
    renderWizard({
      calibrationProgress: { skipped: true, completed: false, samples: [] },
      step: "calibrationSummary"
    });
    await userEvent.click(screen.getByRole("button", { name: /continue setup/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({ onboardingStep: "optional" });
  });

  it("completes onboarding from launch step", async () => {
    const onComplete = vi.fn();
    renderWizard({ onComplete, step: "done" });
    expect(screen.getByRole("heading", { name: "Launch Sabi" })).toBeTruthy();
    expect(screen.getByText(/Control\+Alt\+Space/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /launch sabi/i }));
    expect(window.sabi?.settings.update).toHaveBeenCalledWith({
      onboardingCompleted: true,
      onboardingStep: "done",
      pipeline: "silent"
    });
    expect(onComplete).toHaveBeenCalled();
  });
});
