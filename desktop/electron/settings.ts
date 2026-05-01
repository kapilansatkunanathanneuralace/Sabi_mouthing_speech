import { EventEmitter } from "node:events";
import { copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { z } from "zod";

const onboardingSteps = [
  "account",
  "profile",
  "welcome",
  "camera",
  "cameraDevice",
  "microphone",
  "microphoneDevice",
  "accessibility",
  "shortcut",
  "models",
  "calibrationIntro",
  "calibrationSample",
  "calibrationSummary",
  "optional",
  "done"
] as const;

const onboardingProfileDraftSchema = z.object({
  referralSource: z.string(),
  profession: z.string(),
  useCases: z.array(z.string()),
  workEnvironment: z.string(),
  updatedAt: z.string()
});

const calibrationSampleSchema = z.object({
  sampleId: z.string(),
  text: z.string(),
  status: z.enum(["pending", "passed", "failed", "cancelled"]),
  attempts: z.number().int().min(0),
  updatedAt: z.string(),
  transcript: z.string().optional(),
  error: z.string().optional()
});

const calibrationProgressSchema = z.object({
  skipped: z.boolean(),
  completed: z.boolean(),
  samples: z.array(calibrationSampleSchema)
});

export const settingsSchema = z.object({
  mode: z.enum(["push_to_talk", "toggle"]),
  hotkey: z.string().min(1),
  pipeline: z.enum(["silent", "audio", "fused"]),
  pasteOnAccept: z.boolean(),
  overlayEnabled: z.boolean(),
  onboardingCompleted: z.boolean(),
  onboardingStep: z.enum(onboardingSteps),
  onboardingProfileDraft: onboardingProfileDraftSchema.nullable(),
  cameraIndex: z.number().int().min(0),
  microphoneDeviceIndex: z.number().int().min(0).nullable(),
  shortcutVerified: z.boolean(),
  calibrationProgress: calibrationProgressSchema.nullable()
});

export const settingsPatchSchema = settingsSchema.partial();

export type DesktopSettings = z.infer<typeof settingsSchema>;
export type DesktopSettingsPatch = z.infer<typeof settingsPatchSchema>;
type OnboardingStep = DesktopSettings["onboardingStep"];

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
    onboardingStep: "account",
    onboardingProfileDraft: null,
    cameraIndex: 0,
    microphoneDeviceIndex: null,
    shortcutVerified: false,
    calibrationProgress: null
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function normalizeOnboardingStep(
  value: unknown,
  onboardingCompleted: boolean
): OnboardingStep {
  if (onboardingCompleted) {
    return "done";
  }
  if (typeof value === "string" && onboardingSteps.includes(value as OnboardingStep)) {
    return value as OnboardingStep;
  }
  return "account";
}

export function normalizeSettings(
  raw: unknown,
  platform: NodeJS.Platform = process.platform
): DesktopSettings {
  const defaults = defaultSettings(platform);
  if (!isRecord(raw)) {
    return defaults;
  }
  const merged = { ...defaults, ...raw };
  const onboardingCompleted = raw.onboardingCompleted === true;
  merged.onboardingCompleted = onboardingCompleted;
  merged.onboardingStep = normalizeOnboardingStep(raw.onboardingStep, onboardingCompleted);
  return settingsSchema.parse(merged);
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
      return normalizeSettings(parsed, this.platform);
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
