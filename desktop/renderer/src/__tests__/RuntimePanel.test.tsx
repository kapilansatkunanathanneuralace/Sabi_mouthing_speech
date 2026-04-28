// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RuntimePanel } from "../RuntimePanel";
import type { RuntimeStatus } from "../types/sidecar";

const missingRuntime: RuntimeStatus = {
  state: "missing",
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

function installBridge(status: RuntimeStatus) {
  window.sabi = {
    version: vi.fn(),
    sidecar: {
      status: vi.fn(),
      call: vi.fn(),
      reconnect: vi.fn(),
      onStatus: vi.fn(),
      onNotification: vi.fn()
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
      status: vi.fn(async () => status),
      download: vi.fn(async () => ({ ...status, state: "installed" as const })),
      verify: vi.fn(),
      activate: vi.fn(),
      clear: vi.fn()
    },
    ollama: {
      status: vi.fn(),
      openInstaller: vi.fn(),
      pullModel: vi.fn(),
      onProgress: vi.fn()
    },
    settings: {
      get: vi.fn(),
      update: vi.fn()
    },
    platform: {
      info: vi.fn(),
      openPrivacySettings: vi.fn()
    },
    permissions: {
      accessibilityStatus: vi.fn(),
      mediaStatus: vi.fn()
    }
  };
}

describe("RuntimePanel", () => {
  afterEach(() => cleanup());

  it("installs the full runtime through the preload bridge", async () => {
    installBridge(missingRuntime);
    const onChange = vi.fn();

    render(<RuntimePanel onChange={onChange} runtime={missingRuntime} />);
    await userEvent.click(screen.getByRole("button", { name: /install full runtime/i }));

    expect(window.sabi?.runtime.download).toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ state: "installed" }));
  });
});
