import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("sabi", {
  version: () => ipcRenderer.invoke("app:version") as Promise<string>,
  sidecar: {
    status: () => ipcRenderer.invoke("sidecar:status"),
    call: (method: string, params?: unknown) => ipcRenderer.invoke("sidecar:call", method, params),
    reconnect: () => ipcRenderer.invoke("sidecar:reconnect"),
    onStatus: (callback: (status: unknown) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, status: unknown) => callback(status);
      ipcRenderer.on("sidecar:status", listener);
      return () => ipcRenderer.off("sidecar:status", listener);
    },
    onNotification: (callback: (notification: unknown) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, notification: unknown) =>
        callback(notification);
      ipcRenderer.on("sidecar:notification", listener);
      return () => ipcRenderer.off("sidecar:notification", listener);
    }
  },
  logs: {
    openFolder: () => ipcRenderer.invoke("logs:open-folder") as Promise<string>
  },
  cache: {
    openFolder: () => ipcRenderer.invoke("cache:open-folder") as Promise<string>
  },
  settings: {
    get: () => ipcRenderer.invoke("settings:get"),
    update: (patch: unknown) => ipcRenderer.invoke("settings:update", patch)
  },
  platform: {
    info: () => ipcRenderer.invoke("platform:info"),
    openPrivacySettings: (target: "camera" | "microphone") =>
      ipcRenderer.invoke("platform:open-privacy-settings", target)
  },
  permissions: {
    accessibilityStatus: (prompt = false) =>
      ipcRenderer.invoke("permissions:accessibility-status", prompt),
    mediaStatus: (mediaType: "camera" | "microphone") =>
      ipcRenderer.invoke("permissions:media-status", mediaType)
  }
});
