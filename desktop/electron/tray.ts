import { app, Menu, nativeImage, shell, Tray } from "electron";
import { join } from "node:path";

import type { SidecarStatus } from "./sidecar/types.js";

export interface TrayControllerOptions {
  onOpenSettings: () => void;
  onQuit: () => void;
  onStartDictation: () => void;
  onStopDictation: () => void;
}

export class TrayController {
  private tray: Tray | null = null;
  private status: SidecarStatus = { state: "stopped", restarts: 0 };

  constructor(private readonly options: TrayControllerOptions) {}

  create(): void {
    const iconPath = join(app.getAppPath(), "build", "icons", "tray.svg");
    const image = nativeImage.createFromPath(iconPath);
    this.tray = new Tray(image.resize({ width: 16, height: 16 }));
    this.tray.setToolTip("Sabi: starting");
    this.rebuildMenu();
  }

  updateStatus(status: SidecarStatus): void {
    this.status = status;
    this.tray?.setToolTip(`Sabi: ${status.state}`);
    this.rebuildMenu();
  }

  private rebuildMenu(): void {
    if (!this.tray) {
      return;
    }
    const menu = Menu.buildFromTemplate([
      { label: `Status: ${this.status.state}`, enabled: false },
      { type: "separator" },
      { label: "Start dictation", click: this.options.onStartDictation },
      { label: "Stop dictation", click: this.options.onStopDictation },
      { type: "separator" },
      { label: "Open settings", click: this.options.onOpenSettings },
      {
        label: "Open log folder",
        click: () => {
          void shell.openPath(app.getPath("logs"));
        }
      },
      { type: "separator" },
      { label: "Quit", click: this.options.onQuit }
    ]);
    this.tray.setContextMenu(menu);
  }
}
