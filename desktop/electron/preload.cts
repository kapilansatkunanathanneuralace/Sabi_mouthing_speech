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
  clipboard: {
    writeText: (text: string) => ipcRenderer.invoke("clipboard:write-text", text) as Promise<void>
  },
  dictationHistory: {
    load: () => ipcRenderer.invoke("dictation-history:load"),
    save: (entries: unknown) => ipcRenderer.invoke("dictation-history:save", entries),
    clear: () => ipcRenderer.invoke("dictation-history:clear")
  },
  cache: {
    openFolder: () => ipcRenderer.invoke("cache:open-folder") as Promise<string>
  },
  runtime: {
    status: () => ipcRenderer.invoke("runtime:status"),
    download: (params?: unknown) => ipcRenderer.invoke("runtime:download", params),
    verify: () => ipcRenderer.invoke("runtime:verify"),
    activate: () => ipcRenderer.invoke("runtime:activate"),
    clear: () => ipcRenderer.invoke("runtime:clear")
  },
  ollama: {
    status: () => ipcRenderer.invoke("ollama:status"),
    openInstaller: (params?: unknown) => ipcRenderer.invoke("ollama:open-installer", params),
    pullModel: (params?: unknown) => ipcRenderer.invoke("ollama:pull-model", params),
    onProgress: (callback: (progress: unknown) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, progress: unknown) => callback(progress);
      ipcRenderer.on("ollama:progress", listener);
      return () => ipcRenderer.off("ollama:progress", listener);
    }
  },
  settings: {
    get: () => ipcRenderer.invoke("settings:get"),
    update: (patch: unknown) => ipcRenderer.invoke("settings:update", patch)
  },
  platform: {
    info: () => ipcRenderer.invoke("platform:info"),
    openPrivacySettings: (
      target: "camera" | "microphone" | "accessibility" | "input-monitoring"
    ) =>
      ipcRenderer.invoke("platform:open-privacy-settings", target)
  },
  permissions: {
    accessibilityStatus: (prompt = false) =>
      ipcRenderer.invoke("permissions:accessibility-status", prompt),
    mediaStatus: (mediaType: "camera" | "microphone") =>
      ipcRenderer.invoke("permissions:media-status", mediaType),
    requestMediaAccess: (mediaType: "camera" | "microphone") =>
      ipcRenderer.invoke("permissions:request-media-access", mediaType)
  },
  shortcuts: {
    validate: (accelerator: string) => ipcRenderer.invoke("shortcuts:validate", accelerator),
    test: (accelerator: string, timeoutMs?: number) =>
      ipcRenderer.invoke("shortcuts:test", accelerator, timeoutMs)
  }
});
