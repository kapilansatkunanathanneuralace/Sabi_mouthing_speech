import type { RuntimeStatus } from "./types/sidecar";

export function runtimeReady(runtime: RuntimeStatus | null): boolean {
  return runtime?.state === "installed";
}
