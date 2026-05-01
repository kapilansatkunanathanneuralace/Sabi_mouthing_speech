import type { PlatformInfo } from "../types/sidecar";

export type PermissionState =
  | "idle"
  | "checking"
  | "granted"
  | "denied"
  | "unsupported"
  | "probe_failed"
  | "error";

export interface OsPermissionResult {
  state: PermissionState;
  detail: string;
}

export function classifyMediaStatus(
  status: string,
  platform: PlatformInfo
): OsPermissionResult {
  if (!platform.isMac) {
    return {
      state: "unsupported",
      detail: "This platform does not expose a separate OS media permission check."
    };
  }
  if (status === "granted") {
    return { state: "granted", detail: "OS permission is granted." };
  }
  if (status === "not-determined") {
    return { state: "idle", detail: "OS permission has not been requested yet." };
  }
  if (status === "denied" || status === "restricted") {
    return {
      state: "denied",
      detail: `OS permission is ${status}. Open settings, grant access, then retry.`
    };
  }
  return {
    state: "error",
    detail: `OS permission status is ${status || "unknown"}.`
  };
}

export function statusClass(state: PermissionState): string {
  if (state === "granted") {
    return "check-pass";
  }
  if (state === "denied" || state === "probe_failed" || state === "error") {
    return "check-fail";
  }
  return "check-pending";
}
