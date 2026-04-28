// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CachePanel } from "../CachePanel";

function installBridge() {
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
    cache: { openFolder: vi.fn() },
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

const statusResponse = {
  root: "C:/Users/example/AppData/Local/Sabi/models",
  manifests: [
    {
      manifest: "vsr",
      kind: "vsr",
      description: "Visual speech weights",
      status: "missing",
      root: "C:/Users/example/AppData/Local/Sabi/models/vsr",
      size_bytes: 0,
      entries: [],
      migration_candidate: null
    }
  ]
};

describe("CachePanel", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders cache status and runs verify", async () => {
    installBridge();
    const call = vi.fn(async (method: string) => {
      if (method === "cache.status") {
        return statusResponse;
      }
      return {
        ok: true,
        manifests: [{ ...statusResponse.manifests[0], status: "present" }]
      };
    });

    render(<CachePanel call={call} />);

    expect(await screen.findByText("vsr")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(call).toHaveBeenCalledWith("cache.verify", expect.any(Object)));
  });

  it("opens the model cache folder through the preload bridge", async () => {
    installBridge();
    const call = vi.fn(async () => statusResponse);
    render(<CachePanel call={call} />);

    await userEvent.click(screen.getByRole("button", { name: /open folder/i }));

    expect(window.sabi?.cache.openFolder).toHaveBeenCalled();
  });
});
