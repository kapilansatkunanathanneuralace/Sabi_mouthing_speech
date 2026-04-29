import { useCallback, useEffect, useState } from "react";

import type { JsonRpcParams, JsonValue, SidecarStatus } from "./types/sidecar";

const previewStatus: SidecarStatus = {
  state: "disconnected",
  error: "Electron preload bridge unavailable in browser preview.",
  restarts: 0
};

export function useSidecar() {
  const [status, setStatus] = useState<SidecarStatus>(previewStatus);

  useEffect(() => {
    if (!window.sabi) {
      return undefined;
    }
    void window.sabi.sidecar.status().then(setStatus);
    return window.sabi.sidecar.onStatus(setStatus);
  }, []);

  const call = useCallback(async (method: string, params?: JsonRpcParams): Promise<JsonValue> => {
    if (!window.sabi) {
      throw new Error("Electron preload bridge unavailable.");
    }
    return window.sabi.sidecar.call(method, params);
  }, []);

  const reconnect = useCallback(async () => {
    if (!window.sabi) {
      setStatus(previewStatus);
      return;
    }
    setStatus(await window.sabi.sidecar.reconnect());
  }, []);

  const openLogFolder = useCallback(async () => {
    if (!window.sabi) {
      return;
    }
    await window.sabi.logs.openFolder();
  }, []);

  return {
    call,
    openLogFolder,
    reconnect,
    status,
    version: status.version
  };
}
