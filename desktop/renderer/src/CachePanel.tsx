import { useEffect, useState } from "react";

import type {
  CacheActionResponse,
  CacheManifestStatus,
  CacheStatusResponse,
  JsonRpcParams,
  JsonValue
} from "./types/sidecar";

interface Props {
  call: (method: string, params?: JsonRpcParams) => Promise<JsonValue>;
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  const units = ["KB", "MB", "GB"];
  let size = value / 1024;
  let unit = units[0];
  for (const next of units.slice(1)) {
    if (size < 1024) {
      break;
    }
    size /= 1024;
    unit = next;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`;
}

export function CachePanel({ call }: Props) {
  const [status, setStatus] = useState<CacheStatusResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    setStatus((await call("cache.status")) as unknown as CacheStatusResponse);
  }

  async function runAction(method: "cache.verify" | "cache.download" | "cache.clear", manifest: string) {
    setBusy(`${method}:${manifest}`);
    setError(null);
    try {
      const result = (await call(method, {
        manifest,
        force: method === "cache.download"
      })) as unknown as CacheActionResponse;
      setStatus((current) => ({
        root: current?.root ?? "",
        manifests: mergeManifests(current?.manifests ?? [], result.manifests)
      }));
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    let cancelled = false;
    call("cache.status")
      .then((result) => {
        if (!cancelled) {
          setStatus(result as unknown as CacheStatusResponse);
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : String(loadError));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [call]);

  return (
    <section className="cache-panel" aria-label="Model asset cache">
      <div className="panel-heading">
        <div>
          <h2>Model asset cache</h2>
          <p>Models live outside the installer in Sabi's app-controlled cache.</p>
        </div>
        <div className="actions compact">
          <button type="button" onClick={() => void refresh()}>
            Refresh
          </button>
          <button type="button" onClick={() => void window.sabi?.cache.openFolder()}>
            Open folder
          </button>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="cache-grid">
        {(status?.manifests ?? []).map((manifest) => (
          <article className="cache-card" key={manifest.manifest}>
            <h3>{manifest.manifest}</h3>
            <span className={`status-pill status-${manifest.status}`}>{manifest.status}</span>
            <p>{manifest.description || "No description."}</p>
            <p>Size: {formatBytes(manifest.size_bytes)}</p>
            {manifest.migration_candidate ? (
              <small>Existing dev cache detected: {manifest.migration_candidate}</small>
            ) : null}
            <div className="actions compact">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void runAction("cache.verify", manifest.manifest)}
              >
                Verify
              </button>
              <button
                type="button"
                disabled={busy !== null || manifest.status === "unsupported"}
                onClick={() => void runAction("cache.download", manifest.manifest)}
              >
                Re-download
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void runAction("cache.clear", manifest.manifest)}
              >
                Clear
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function mergeManifests(
  current: CacheManifestStatus[],
  updates: CacheManifestStatus[]
): CacheManifestStatus[] {
  const byName = new Map(current.map((item) => [item.manifest, item]));
  for (const update of updates) {
    byName.set(update.manifest, update);
  }
  return Array.from(byName.values());
}
