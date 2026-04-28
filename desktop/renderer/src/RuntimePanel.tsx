import { runtimeReady } from "./runtimeStatus";
import type { RuntimeStatus } from "./types/sidecar";

interface Props {
  onChange: (status: RuntimeStatus) => void;
  runtime: RuntimeStatus | null;
}

export function RuntimePanel({ onChange, runtime }: Props) {
  async function refresh() {
    const status = await window.sabi?.runtime.status();
    if (status) {
      onChange(status);
    }
  }

  async function install() {
    const status = await window.sabi?.runtime.download();
    if (status) {
      onChange(status);
    }
  }

  async function clear() {
    const status = await window.sabi?.runtime.clear();
    if (status) {
      onChange(status);
    }
  }

  return (
    <section className="cache-panel" aria-label="Full dictation runtime">
      <div className="panel-heading">
        <div>
          <h2>Full dictation runtime</h2>
          <p>
            The installer includes a slim bootstrap sidecar. Silent/audio/fused dictation needs
            the full CPU runtime pack.
          </p>
        </div>
        <span className={`status-pill status-${runtime?.state ?? "missing"}`}>
          {runtime?.state ?? "missing"}
        </span>
      </div>
      {runtime?.message ? <p className="error">{runtime.message}</p> : null}
      {runtime ? (
        <p>
          {runtime.manifest.description} Version {runtime.manifest.version}.
        </p>
      ) : null}
      <div className="actions compact">
        <button type="button" onClick={() => void refresh()}>
          Refresh
        </button>
        <button type="button" disabled={runtimeReady(runtime)} onClick={() => void install()}>
          Install full runtime
        </button>
        <button type="button" disabled={!runtimeReady(runtime)} onClick={() => void clear()}>
          Clear runtime
        </button>
      </div>
    </section>
  );
}
