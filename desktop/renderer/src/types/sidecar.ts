export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonRpcParams = Record<string, JsonValue> | JsonValue[] | null | undefined;

export interface SidecarVersion {
  protocol_version: string;
  app_version: string;
}

export type SidecarState = "starting" | "connected" | "disconnected" | "crashed" | "stopped";

export interface SidecarStatus {
  state: SidecarState;
  version?: SidecarVersion;
  error?: string;
  pid?: number;
  restarts: number;
}

export interface SidecarNotification {
  method: string;
  params?: JsonValue;
}

export interface ProbeResult {
  runtime: Record<string, string>;
  imports: Array<{ module: string; ok: boolean; detail: string }>;
  torch: Record<string, JsonValue>;
  webcam: Record<string, JsonValue>;
  audio: Record<string, JsonValue>;
  failures: number;
}

export interface ProbeResponse {
  probe: ProbeResult;
}

export type DesktopMode = "push_to_talk" | "toggle";
export type DesktopPipeline = "silent" | "audio" | "fused";
export type OnboardingStep =
  | "welcome"
  | "camera"
  | "microphone"
  | "accessibility"
  | "models"
  | "optional"
  | "done";

export interface DesktopSettings {
  mode: DesktopMode;
  hotkey: string;
  pipeline: DesktopPipeline;
  pasteOnAccept: boolean;
  overlayEnabled: boolean;
  onboardingCompleted: boolean;
  onboardingStep: OnboardingStep;
}

export type DesktopSettingsPatch = Partial<DesktopSettings>;

export interface PlatformInfo {
  platform: string;
  isMac: boolean;
  isWindows: boolean;
}

export type CacheAssetStatus = "present" | "missing" | "corrupt" | "unsupported";

export interface CacheEntry {
  name: string;
  kind: string;
  relative_path: string;
  path: string;
  status: CacheAssetStatus;
  size_bytes: number;
  sha256?: string | null;
  expected_sha256: string;
}

export interface CacheManifestStatus {
  manifest: string;
  kind: string;
  description: string;
  status: CacheAssetStatus;
  root: string;
  size_bytes: number;
  entries: CacheEntry[];
  migration_candidate?: string | null;
}

export interface CacheStatusResponse {
  root: string;
  manifests: CacheManifestStatus[];
}

export interface CacheActionResponse {
  ok: boolean;
  manifests: CacheManifestStatus[];
}
