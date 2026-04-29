// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OllamaPanel } from "../OllamaPanel";
import type { OllamaStatus } from "../types/sidecar";

const missingModel: OllamaStatus = {
  cliFound: true,
  apiReachable: true,
  baseUrl: "http://127.0.0.1:11434",
  model: "llama3.2:3b-instruct-q4_K_M",
  modelPresent: false,
  installed: true,
  ready: false,
  detail: "Ollama is running, but the model has not been pulled yet.",
  models: []
};

const readyModel: OllamaStatus = {
  ...missingModel,
  modelPresent: true,
  ready: true,
  detail: "Ollama is ready with llama3.2:3b-instruct-q4_K_M."
};

function installBridge(status = vi.fn(async () => missingModel)) {
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
      status: vi.fn(),
      download: vi.fn(),
      verify: vi.fn(),
      activate: vi.fn(),
      clear: vi.fn()
    },
    ollama: {
      status,
      openInstaller: vi.fn(),
      pullModel: vi.fn(async () => ({ ok: true, model: missingModel.model, exitCode: 0 })),
      onProgress: vi.fn(() => () => undefined)
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

describe("OllamaPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows Ollama status and opens the official installer with consent", async () => {
    installBridge();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<OllamaPanel />);

    expect(await screen.findByText(/has not been pulled/i)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /install ollama/i }));

    expect(window.sabi?.ollama.openInstaller).toHaveBeenCalledWith({ consent: true });
  });

  it("pulls the configured model after consent and refreshes status", async () => {
    const status = vi.fn().mockResolvedValueOnce(missingModel).mockResolvedValueOnce(readyModel);
    installBridge(status);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<OllamaPanel />);

    await screen.findByText(/has not been pulled/i);
    await userEvent.click(screen.getByRole("button", { name: /pull cleanup model/i }));

    await waitFor(() =>
      expect(window.sabi?.ollama.pullModel).toHaveBeenCalledWith({ consent: true })
    );
    await waitFor(() => expect(screen.getByText(/ready with/i)).toBeTruthy());
  });
});
