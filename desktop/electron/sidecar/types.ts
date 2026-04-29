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
