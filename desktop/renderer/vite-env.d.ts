/// <reference types="vite/client" />

import type {
  DesktopSettings,
  DesktopSettingsPatch,
  JsonRpcParams,
  JsonValue,
  PlatformInfo,
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
      cache: {
        openFolder: () => Promise<string>;
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
