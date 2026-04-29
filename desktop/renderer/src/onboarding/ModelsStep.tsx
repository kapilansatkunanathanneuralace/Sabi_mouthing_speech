import { useState } from "react";

import { RuntimePanel } from "../RuntimePanel";
import { runtimeReady } from "../runtimeStatus";
import { nextStep } from "./steps";
import type { ModelsStepProps } from "./types";

export function ModelsStep({
  callModelDownload,
  goTo,
  notifications,
  platform,
  runtime,
  setRuntime
}: ModelsStepProps) {
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = notifications
    .filter(
      (item) =>
        item.method === "cache.download.progress" || item.method === "models.download_vsr.progress"
    )
    .at(-1);
  const params = latest?.params;
  const index = params && typeof params === "object" && !Array.isArray(params) ? Number(params.index ?? 0) : 0;
  const total = params && typeof params === "object" && !Array.isArray(params) ? Number(params.total ?? 1) : 1;
  const status = params && typeof params === "object" && !Array.isArray(params) ? String(params.status ?? "") : "";
  const percent = total > 0 ? Math.round((index / total) * 100) : 0;

  async function download() {
    setRunning(true);
    setError(null);
    try {
      const ok = await callModelDownload();
      setDone(ok);
      if (!ok) {
        setError("Model download failed. Retry after checking your network connection.");
      }
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : String(downloadError));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="wizard-step">
      <h2>Download visual speech models</h2>
      <p>
        Sabi downloads model assets locally and installs a full CPU runtime before enabling
        real dictation.
      </p>
      <RuntimePanel onChange={setRuntime} runtime={runtime} />
      <div className="progress-shell">
        <div className="progress-bar" style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
      <p>{status || (done ? "Models are ready." : "Ready to download.")}</p>
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button type="button" onClick={() => void download()} disabled={running}>
          {running ? "Downloading..." : "Download models"}
        </button>
        <button
          type="button"
          disabled={!done || !runtimeReady(runtime)}
          onClick={() => void goTo(nextStep("models", platform))}
        >
          Next
        </button>
      </div>
    </div>
  );
}
