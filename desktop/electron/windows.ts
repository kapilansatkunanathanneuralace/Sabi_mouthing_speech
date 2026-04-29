import { BrowserWindow } from "electron";
import { pathToFileURL } from "node:url";

import type { DesktopSettings } from "./settings.js";

export interface WindowManagerOptions {
  devServerUrl?: string;
  preloadPath: string;
  rendererHtmlPath: string;
}

export class WindowManager {
  private settingsWindow: BrowserWindow | null = null;
  private overlayWindow: BrowserWindow | null = null;
  private quitting = false;

  constructor(private readonly options: WindowManagerOptions) {}

  showSettings(): void {
    const window = this.getSettingsWindow();
    if (window.isMinimized()) {
      window.restore();
    }
    window.show();
    window.focus();
  }

  applySettings(settings: DesktopSettings): void {
    const overlay = this.getOverlayWindow();
    if (settings.overlayEnabled) {
      overlay.showInactive();
    } else {
      overlay.hide();
    }
  }

  allowQuit(): void {
    this.quitting = true;
  }

  getSettingsWindow(): BrowserWindow {
    if (this.settingsWindow && !this.settingsWindow.isDestroyed()) {
      return this.settingsWindow;
    }
    this.settingsWindow = new BrowserWindow({
      width: 1024,
      height: 720,
      show: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: this.options.preloadPath
      }
    });
    this.settingsWindow.on("close", (event) => {
      if (this.quitting) {
        return;
      }
      event.preventDefault();
      this.settingsWindow?.hide();
    });
    this.loadRenderer(this.settingsWindow);
    return this.settingsWindow;
  }

  private getOverlayWindow(): BrowserWindow {
    if (this.overlayWindow && !this.overlayWindow.isDestroyed()) {
      return this.overlayWindow;
    }
    this.overlayWindow = new BrowserWindow({
      width: 520,
      height: 160,
      show: false,
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      skipTaskbar: true,
      focusable: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: this.options.preloadPath
      }
    });
    this.overlayWindow.setIgnoreMouseEvents(true, { forward: true });
    this.loadRenderer(this.overlayWindow);
    return this.overlayWindow;
  }

  private loadRenderer(window: BrowserWindow): void {
    if (this.options.devServerUrl) {
      void window.loadURL(this.options.devServerUrl);
      return;
    }
    const url = pathToFileURL(this.options.rendererHtmlPath);
    if (process.env.SABI_RENDERER_SMOKE === "1") {
      url.searchParams.set("sabiSmoke", "1");
    }
    void window.loadURL(url.toString());
  }
}
