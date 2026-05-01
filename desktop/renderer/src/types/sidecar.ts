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
export type DictationPipeline = DesktopPipeline | "vsr";
export type PrivacySettingsTarget =
  | "camera"
  | "microphone"
  | "accessibility"
  | "input-monitoring";
export type OnboardingStep =
  | "account"
  | "profile"
  | "welcome"
  | "camera"
  | "cameraDevice"
  | "microphone"
  | "microphoneDevice"
  | "accessibility"
  | "shortcut"
  | "models"
  | "calibrationIntro"
  | "calibrationSample"
  | "calibrationSummary"
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
  onboardingProfileDraft: OnboardingProfileDraft | null;
  cameraIndex: number;
  microphoneDeviceIndex: number | null;
  shortcutVerified: boolean;
  calibrationProgress: CalibrationProgress | null;
}

export type DesktopSettingsPatch = Partial<DesktopSettings>;

export interface OnboardingProfileDraft {
  referralSource: string;
  profession: string;
  useCases: string[];
  workEnvironment: string;
  updatedAt: string;
}

export type CalibrationSampleStatus = "pending" | "passed" | "failed" | "cancelled";

export interface CalibrationSampleProgress {
  sampleId: string;
  text: string;
  status: CalibrationSampleStatus;
  attempts: number;
  updatedAt: string;
  transcript?: string;
  error?: string;
}

export interface CalibrationProgress {
  skipped: boolean;
  completed: boolean;
  samples: CalibrationSampleProgress[];
}

export interface CalibrationSamplePlan {
  sample_id: string;
  text: string;
  index: number;
  total: number;
  mode: "optional";
}

export interface CalibrationPlanResponse {
  samples: CalibrationSamplePlan[];
}

export interface CalibrationRunResponse {
  sample_id: string;
  text: string;
  mode: "optional";
  ok: boolean;
  status: "passed" | "failed" | "cancelled";
  transcript: string;
  error: string | null;
  quality: Record<string, JsonValue>;
}

export interface PlatformInfo {
  platform: string;
  isMac: boolean;
  isWindows: boolean;
}

export interface ProbeDevice {
  kind: "camera" | "microphone";
  index: number;
  name: string;
  available: boolean;
  detail?: string;
}

export interface ProbeDevicesResponse {
  cameras: ProbeDevice[];
  microphones: ProbeDevice[];
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

export type RuntimeState = "missing" | "available" | "installed" | "corrupt" | "unsupported";

export interface RuntimeManifest {
  name: string;
  version: string;
  platform: string;
  arch: string;
  min_desktop_version: string;
  url: string;
  sha256: string;
  size_bytes: number;
  artifact: string;
  sidecar_dir: string;
  description: string;
}

export interface RuntimeStatus {
  state: RuntimeState;
  root: string;
  active_dir: string;
  sidecar_bin: string;
  manifest: RuntimeManifest;
  message?: string;
}

export interface RuntimeDownloadParams {
  url?: string;
  path?: string;
  force?: boolean;
}

export interface OllamaStatus {
  cliFound: boolean;
  cliPath?: string;
  apiReachable: boolean;
  baseUrl: string;
  model: string;
  modelPresent: boolean;
  installed: boolean;
  ready: boolean;
  detail: string;
  models: string[];
}

export interface OllamaProgress {
  model: string;
  stream: "stdout" | "stderr" | "status";
  message: string;
}

export interface OllamaPullResult {
  ok: boolean;
  model: string;
  exitCode: number | null;
}

export interface DictationUtterancePayload {
  pipeline?: DictationPipeline;
  utterance_id?: number;
  started_at_ns?: number;
  ended_at_ns?: number;
  text_raw?: string;
  text_final?: string;
  confidence?: number;
  used_fallback?: boolean;
  decision?: string;
  error?: string | null;
  asr?: JsonValue;
  vsr?: JsonValue;
  fusion?: JsonValue;
  latencies?: Record<string, number>;
}

export interface DictationHistoryEntry {
  id: string;
  createdAt: string;
  pipeline: DictationPipeline;
  utteranceId?: number;
  textRaw: string;
  textFinal: string;
  confidence?: number;
  decision?: string;
  status: "accepted" | "withheld" | "dry_run" | "error";
  error?: string | null;
  payload: DictationUtterancePayload;
}
