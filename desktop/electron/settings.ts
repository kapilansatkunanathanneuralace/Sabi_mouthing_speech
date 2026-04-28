import { EventEmitter } from "node:events";
import { copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { z } from "zod";

export const settingsSchema = z.object({
  mode: z.enum(["push_to_talk", "toggle"]),
  hotkey: z.string().min(1),
  pipeline: z.enum(["silent", "audio", "fused"]),
  pasteOnAccept: z.boolean(),
  overlayEnabled: z.boolean(),
  onboardingCompleted: z.boolean(),
  onboardingStep: z.enum([
    "welcome",
    "camera",
    "microphone",
    "accessibility",
    "models",
    "optional",
    "done"
  ])
});

export const settingsPatchSchema = settingsSchema.partial();

export type DesktopSettings = z.infer<typeof settingsSchema>;
export type DesktopSettingsPatch = z.infer<typeof settingsPatchSchema>;

export function defaultHotkey(platform: NodeJS.Platform = process.platform): string {
  return platform === "darwin" ? "CommandOrControl+Alt+Space" : "Control+Alt+Space";
}

export function defaultSettings(platform: NodeJS.Platform = process.platform): DesktopSettings {
  return {
    mode: "push_to_talk",
    hotkey: defaultHotkey(platform),
    pipeline: "silent",
    pasteOnAccept: true,
    overlayEnabled: false,
    onboardingCompleted: false,
    onboardingStep: "welcome"
  };
}

export class SettingsStore extends EventEmitter {
  private current: DesktopSettings;
  readonly filePath: string;

  constructor(
    userDataDir: string,
    private readonly platform: NodeJS.Platform = process.platform
  ) {
    super();
    mkdirSync(userDataDir, { recursive: true });
    this.filePath = join(userDataDir, "settings.json");
    this.current = this.load();
  }

  get(): DesktopSettings {
    return { ...this.current };
  }

  update(patch: DesktopSettingsPatch): DesktopSettings {
    const parsedPatch = settingsPatchSchema.parse(patch);
    const next = settingsSchema.parse({ ...this.current, ...parsedPatch });
    this.current = next;
    this.save(next);
    this.emit("change", this.get());
    return this.get();
  }

  private load(): DesktopSettings {
    if (!existsSync(this.filePath)) {
      const defaults = defaultSettings(this.platform);
      this.save(defaults);
      return defaults;
    }
    try {
      const parsed = JSON.parse(readFileSync(this.filePath, "utf-8"));
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("settings file must contain an object");
      }
      return settingsSchema.parse({ ...defaultSettings(this.platform), ...parsed });
    } catch {
      this.quarantineCorruptFile();
      const defaults = defaultSettings(this.platform);
      this.save(defaults);
      return defaults;
    }
  }

  private save(settings: DesktopSettings): void {
    writeFileSync(this.filePath, `${JSON.stringify(settings, null, 2)}\n`, "utf-8");
  }

  private quarantineCorruptFile(): void {
    const badPath = `${this.filePath}.${Date.now()}.bad`;
    try {
      renameSync(this.filePath, badPath);
    } catch {
      copyFileSync(this.filePath, badPath);
    }
  }
}
