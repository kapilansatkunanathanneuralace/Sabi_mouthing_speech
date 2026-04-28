import { app, BrowserWindow, ipcMain, Menu, shell, systemPreferences } from "electron";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { ShortcutController } from "./shortcuts.js";
import { SidecarHealth } from "./sidecar/health.js";
import { SidecarProcess } from "./sidecar/process.js";
import type { JsonRpcParams } from "./sidecar/types.js";
import { SettingsStore, type DesktopSettingsPatch } from "./settings.js";
import { TrayController } from "./tray.js";
import { WindowManager } from "./windows.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const devServerUrl = process.env.VITE_DEV_SERVER_URL;

const sidecar = new SidecarProcess();
const health = new SidecarHealth(sidecar);
const singleInstanceLock = app.requestSingleInstanceLock();
let settingsStore: SettingsStore | null = null;
let windows: WindowManager | null = null;
let tray: TrayController | null = null;
let shortcuts: ShortcutController | null = null;

ipcMain.handle("app:version", () => app.getVersion());
ipcMain.handle("sidecar:status", () => sidecar.snapshot());
ipcMain.handle("sidecar:call", (_event, method: string, params?: JsonRpcParams) =>
  sidecar.call(method, params)
);
ipcMain.handle("sidecar:reconnect", () => health.reconnect());
ipcMain.handle("logs:open-folder", () => shell.openPath(app.getPath("logs")));
ipcMain.handle("cache:open-folder", () => shell.openPath(modelCacheRoot()));
ipcMain.handle("settings:get", () => settingsStore?.get());
ipcMain.handle("settings:update", (_event, patch: DesktopSettingsPatch) =>
  settingsStore?.update(patch)
);
ipcMain.handle("platform:info", () => ({
  platform: process.platform,
  isMac: process.platform === "darwin",
  isWindows: process.platform === "win32"
}));
ipcMain.handle("permissions:accessibility-status", (_event, prompt = false) => {
  if (process.platform !== "darwin") {
    return { supported: false, granted: true };
  }
  return {
    supported: true,
    granted: systemPreferences.isTrustedAccessibilityClient(Boolean(prompt))
  };
});
ipcMain.handle("permissions:media-status", (_event, mediaType: "camera" | "microphone") => {
  if (process.platform !== "darwin") {
    return { supported: false, status: "unknown" };
  }
  return { supported: true, status: systemPreferences.getMediaAccessStatus(mediaType) };
});
ipcMain.handle("platform:open-privacy-settings", (_event, target: "camera" | "microphone") => {
  const path = target === "camera" ? "ms-settings:privacy-webcam" : "ms-settings:privacy-microphone";
  return shell.openExternal(path);
});

function modelCacheRoot(): string {
  if (process.env.SABI_MODELS_DIR) {
    return process.env.SABI_MODELS_DIR;
  }
  if (process.platform === "win32") {
    return join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "Sabi", "models");
  }
  if (process.platform === "darwin") {
    return join(homedir(), "Library", "Application Support", "Sabi", "models");
  }
  return join(process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"), "sabi", "models");
}

function installMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: "Sabi",
      submenu: [
        {
          label: "Open Settings",
          click: () => windows?.showSettings()
        },
        {
          label: "Open Log Folder",
          click: () => {
            void shell.openPath(app.getPath("logs"));
          }
        },
        { type: "separator" },
        { role: "quit" }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

if (!singleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    windows?.showSettings();
  });
}

if (singleInstanceLock) {
  app.whenReady().then(() => {
    settingsStore = new SettingsStore(app.getPath("userData"));
    windows = new WindowManager({
      devServerUrl,
      preloadPath: join(__dirname, "preload.cjs"),
      rendererHtmlPath: join(__dirname, "../dist-renderer/index.html")
    });
    shortcuts = new ShortcutController(settingsStore, sidecar);
    tray = new TrayController({
      onOpenSettings: () => windows?.showSettings(),
      onQuit: () => {
        windows?.allowQuit();
        shortcuts?.unregister();
        health.stop();
        app.quit();
      },
      onStartDictation: () => {
        void shortcuts?.start();
      },
      onStopDictation: () => {
        void shortcuts?.stop();
      }
    });
    tray.create();
    shortcuts.register();
    windows.applySettings(settingsStore.get());
    settingsStore.on("change", (settings) => windows?.applySettings(settings));
    sidecar.on("status", (status) => tray?.updateStatus(status));
    sidecar.on("notification", (notification) => {
      for (const window of BrowserWindow.getAllWindows()) {
        window.webContents.send("sidecar:notification", notification);
      }
    });
    installMenu();
    health.start();
    windows.showSettings();

    app.on("activate", () => {
      windows?.showSettings();
    });
  });
}

app.on("window-all-closed", () => undefined);

app.on("before-quit", () => {
  windows?.allowQuit();
  shortcuts?.unregister();
  health.stop();
});
