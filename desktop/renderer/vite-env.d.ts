/// <reference types="vite/client" />

import type {
  DictationHistoryEntry,
  DesktopSettings,
  DesktopSettingsPatch,
  JsonRpcParams,
  JsonValue,
  PlatformInfo,
  RuntimeDownloadParams,
  RuntimeStatus,
  OllamaProgress,
  OllamaPullResult,
  OllamaStatus,
  SidecarNotification,
  SidecarStatus
} from "./src/types/sidecar";

declare global {
  interface Window {
    sabi?: {
      version: () => Promise<string>;
      sidecar: {
        status: () => Promise<SidecarStatus>;
        call: (method: string, params?: JsonRpcParams) => Promise<JsonValue>;
        reconnect: () => Promise<SidecarStatus>;
        onStatus: (callback: (status: SidecarStatus) => void) => () => void;
        onNotification: (callback: (notification: SidecarNotification) => void) => () => void;
      };
      logs: {
        openFolder: () => Promise<string>;
      };
      clipboard: {
        writeText: (text: string) => Promise<void>;
      };
      dictationHistory: {
        load: () => Promise<DictationHistoryEntry[]>;
        save: (entries: DictationHistoryEntry[]) => Promise<void>;
        clear: () => Promise<void>;
      };
      cache: {
        openFolder: () => Promise<string>;
      };
      runtime: {
        status: () => Promise<RuntimeStatus>;
        download: (params?: RuntimeDownloadParams) => Promise<RuntimeStatus>;
        verify: () => Promise<RuntimeStatus>;
        activate: () => Promise<RuntimeStatus>;
        clear: () => Promise<RuntimeStatus>;
      };
      ollama: {
        status: () => Promise<OllamaStatus>;
        openInstaller: (
          params?: { consent?: boolean }
        ) => Promise<{ opened: boolean; url: string }>;
        pullModel: (params?: { consent?: boolean }) => Promise<OllamaPullResult>;
        onProgress: (callback: (progress: OllamaProgress) => void) => () => void;
      };
      settings: {
        get: () => Promise<DesktopSettings>;
        update: (patch: DesktopSettingsPatch) => Promise<DesktopSettings>;
      };
      platform: {
        info: () => Promise<PlatformInfo>;
        openPrivacySettings: (target: "camera" | "microphone") => Promise<void>;
      };
      permissions: {
        accessibilityStatus: (
          prompt?: boolean
        ) => Promise<{ supported: boolean; granted: boolean }>;
        mediaStatus: (
          mediaType: "camera" | "microphone"
        ) => Promise<{ supported: boolean; status: string }>;
      };
    };
  }
}

export {};
