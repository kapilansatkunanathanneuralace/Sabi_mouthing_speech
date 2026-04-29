import { useCallback, useEffect, useMemo, useState } from "react";

import type { OllamaProgress, OllamaStatus } from "./types/sidecar";

interface OllamaPanelProps {
  compact?: boolean;
}

export function OllamaPanel({ compact = false }: OllamaPanelProps) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<OllamaProgress[]>([]);

  const statusClass = useMemo(() => {
    if (!status) {
      return "status-missing";
    }
    if (status.ready) {
      return "status-present";
    }
    if (status.apiReachable || status.cliFound) {
      return "status-missing";
    }
    return "status-unsupported";
  }, [status]);

  const refresh = useCallback(async () => {
    if (!window.sabi) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setStatus(await window.sabi.ollama.status());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!window.sabi) {
      return undefined;
    }
    const timeout = window.setTimeout(() => void refresh(), 0);
    const unsubscribe = window.sabi.ollama.onProgress((item) => {
      setProgress((items) => [...items.slice(-7), item]);
    });
    return () => {
      window.clearTimeout(timeout);
      unsubscribe();
    };
  }, [refresh]);

  async function openInstaller() {
    const confirmed = window.confirm(
      "Ollama installs a local background runtime. Continue to the official Ollama installer?"
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      await window.sabi?.ollama.openInstaller({ consent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function pullModel() {
    const model = status?.model ?? "the configured cleanup model";
    const message = `Download ${model} with Ollama? This may use several GB of disk space outside Sabi's cache.`;
    if (!window.confirm(message)) {
      return;
    }
    setPulling(true);
    setError(null);
    setProgress([]);
    try {
      const result = await window.sabi?.ollama.pullModel({ consent: true });
      if (result && !result.ok) {
        setError(`ollama pull exited with ${result.exitCode ?? "unknown status"}.`);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPulling(false);
    }
  }

  return (
    <section
      className={compact ? "ollama-panel compact" : "ollama-panel"}
      aria-label="Ollama setup"
    >
      <div className="panel-heading">
        <div>
          <h2>Ollama cleanup</h2>
          <p>
            Optional local LLM cleanup improves punctuation and filler removal.
            Dictation still works without it.
          </p>
        </div>
        <span className={`status-pill ${statusClass}`}>
          {status?.ready ? "Ready" : status?.installed ? "Setup needed" : "Optional"}
        </span>
      </div>
      <div className="ollama-status">
        <p>{status?.detail ?? "Checking Ollama status..."}</p>
        {status ? (
          <small>
            Model <code>{status.model}</code> at <code>{status.baseUrl}</code>
          </small>
        ) : null}
      </div>
      <div className="actions compact">
        <button type="button" onClick={() => void refresh()} disabled={loading || pulling}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
        <button type="button" onClick={() => void openInstaller()} disabled={pulling}>
          Install Ollama
        </button>
        <button
          type="button"
          onClick={() => void pullModel()}
          disabled={pulling || !status?.apiReachable || status.modelPresent}
          title={!status?.apiReachable ? "Start Ollama before pulling the cleanup model." : undefined}
        >
          {pulling ? "Pulling..." : status?.modelPresent ? "Model ready" : "Pull cleanup model"}
        </button>
      </div>
      {progress.length > 0 ? (
        <pre className="ollama-progress" aria-label="Ollama progress">
          {progress.map((item) => item.message.trim()).filter(Boolean).join("\n")}
        </pre>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
