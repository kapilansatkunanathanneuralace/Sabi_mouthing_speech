import type { ProbeResponse } from "../types/sidecar";
import type { ProbeTarget } from "./types";

export function probePassed(response: ProbeResponse, target: ProbeTarget): boolean {
  if (target === "camera") {
    return Boolean(response.probe.webcam.ok);
  }
  return Boolean(response.probe.audio.ok);
}

export function probeSummary(response: ProbeResponse, target: ProbeTarget): string {
  const payload = target === "camera" ? response.probe.webcam : response.probe.audio;
  const output = payload.output;
  if (typeof output === "string" && output.trim()) {
    return output;
  }
  return probePassed(response, target) ? "Probe passed." : "Probe failed.";
}
