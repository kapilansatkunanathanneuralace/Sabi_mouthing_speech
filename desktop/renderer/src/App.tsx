import { useEffect, useState } from "react";

import { CachePanel } from "./CachePanel";
import { OnboardingWizard } from "./onboarding/OnboardingWizard";
import type { JsonRpcParams, JsonValue } from "./types/sidecar";
import type { DesktopSettings, PlatformInfo, ProbeResponse } from "./types/sidecar";
import { useSidecar } from "./useSidecar";

function App() {
  const { call, openLogFolder, reconnect, status, version } = useSidecar();
  const [settings, setSettings] = useState<DesktopSettings | null>(null);
  const [platform, setPlatform] = useState<PlatformInfo | null>(null);
  const [probe, setProbe] = useState<ProbeResponse | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probeLoading, setProbeLoading] = useState(false);

  useEffect(() => {
    if (!window.sabi) {
      return;
    }
    void window.sabi.settings.get().then(setSettings);
    void window.sabi.platform.info().then(setPlatform);
  }, []);

  async function runProbe() {
    setProbeLoading(true);
    setProbeError(null);
    try {
      setProbe((await call("probe.run", { camera_index: 0 })) as unknown as ProbeResponse);
    } catch (error) {
      setProbeError(error instanceof Error ? error.message : String(error));
    } finally {
      setProbeLoading(false);
    }
  }

  async function startSilentDryRun() {
    const pipeline = settings?.pipeline ?? "silent";
    await call(`dictation.${pipeline}.start`, { dry_run: true });
    window.setTimeout(() => {
      void call(`dictation.${pipeline}.stop`);
    }, 500);
  }

  async function updateSettings(patch: Partial<DesktopSettings>) {
    if (!window.sabi) {
      return;
    }
    setSettings(await window.sabi.settings.update(patch));
  }

  return (
    <main className="shell">
      <section className="card" aria-labelledby="app-title">
        <p className="eyebrow">Sabi Desktop Alpha</p>
        <h1 id="app-title">
          {settings && !settings.onboardingCompleted
            ? "Let's get Sabi ready for first dictation."
            : "Electron is connected to the local Sabi sidecar."}
        </h1>
        <p className="lede">
          The desktop shell owns the Python sidecar process, talks JSON-RPC over stdio, and keeps
          the renderer isolated from Node APIs.
        </p>
        <div className="status-row">
          <span className="version">
            Sidecar {version ? `protocol ${version.protocol_version} / app ${version.app_version}` : "pending"}
          </span>
          <span className={`status-pill status-${status.state}`}>Status: {status.state}</span>
          {status.pid ? <span className="version">PID {status.pid}</span> : null}
        </div>
        {status.state !== "connected" ? (
          <div className="banner">
            <span>{status.error ?? "Waiting for the sidecar to connect."}</span>
            <button type="button" onClick={() => void reconnect()}>
              Reconnect
            </button>
          </div>
        ) : null}
        {settings && platform && !settings.onboardingCompleted ? (
          <OnboardingWizard
            call={call}
            onComplete={setSettings}
            platform={platform}
            settings={settings}
          />
        ) : (
          <Dashboard
            call={call}
            openLogFolder={openLogFolder}
            probe={probe}
            probeError={probeError}
            probeLoading={probeLoading}
            runProbe={runProbe}
            settings={settings}
            startSilentDryRun={startSilentDryRun}
            updateSettings={updateSettings}
          />
        )}
      </section>
    </main>
  );
}

interface DashboardProps {
  call: (method: string, params?: JsonRpcParams) => Promise<JsonValue>;
  openLogFolder: () => Promise<void>;
  probe: ProbeResponse | null;
  probeError: string | null;
  probeLoading: boolean;
  runProbe: () => Promise<void>;
  settings: DesktopSettings | null;
  startSilentDryRun: () => Promise<void>;
  updateSettings: (patch: Partial<DesktopSettings>) => Promise<void>;
}

function Dashboard({
  call,
  openLogFolder,
  probe,
  probeError,
  probeLoading,
  runProbe,
  settings,
  startSilentDryRun,
  updateSettings
}: DashboardProps) {
  return (
    <>
        <div className="actions">
          <button type="button" onClick={() => void runProbe()} disabled={probeLoading}>
            {probeLoading ? "Running probe..." : "Run probe"}
          </button>
          <button type="button" onClick={() => void startSilentDryRun()}>
            Start silent dry-run
          </button>
          <button type="button" onClick={() => void openLogFolder()}>
            Open log folder
          </button>
        </div>
        {settings ? (
          <section className="settings-panel" aria-label="Desktop settings">
            <h2>Desktop settings</h2>
            <label>
              Shortcut mode
              <select
                value={settings.mode}
                onChange={(event) => void updateSettings({ mode: event.target.value as DesktopSettings["mode"] })}
              >
                <option value="push_to_talk">Push to talk (press again to stop)</option>
                <option value="toggle">Toggle</option>
              </select>
            </label>
            <label>
              Pipeline
              <select
                value={settings.pipeline}
                onChange={(event) =>
                  void updateSettings({ pipeline: event.target.value as DesktopSettings["pipeline"] })
                }
              >
                <option value="silent">Silent</option>
                <option value="audio">Audio</option>
                <option value="fused">Fused</option>
              </select>
            </label>
            <label>
              Hotkey
              <input
                value={settings.hotkey}
                onChange={(event) => void updateSettings({ hotkey: event.target.value })}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={settings.pasteOnAccept}
                onChange={(event) => void updateSettings({ pasteOnAccept: event.target.checked })}
              />
              Paste accepted dictation
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={settings.overlayEnabled}
                onChange={(event) => void updateSettings({ overlayEnabled: event.target.checked })}
              />
              Enable overlay stub
            </label>
          </section>
        ) : null}
        <CachePanel call={call} />
        {probeError ? <p className="error">{probeError}</p> : null}
        {probe ? (
          <section className="probe" aria-label="Probe results">
            <h2>Probe results</h2>
            <div className="probe-grid">
              <ResultCard title="Runtime" rows={Object.entries(probe.probe.runtime)} />
              <ResultCard title="Torch" rows={Object.entries(probe.probe.torch)} />
              <ResultCard title="Webcam" rows={Object.entries(probe.probe.webcam)} />
              <ResultCard title="Audio" rows={Object.entries(probe.probe.audio)} />
            </div>
            <h3>Imports</h3>
            <ul className="imports">
              {probe.probe.imports.map((row) => (
                <li key={row.module}>
                  <strong>{row.module}</strong>
                  <span>{row.ok ? "PASS" : "FAIL"}</span>
                  {row.detail ? <small>{row.detail}</small> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
    </>
  );
}

function ResultCard({ title, rows }: { title: string; rows: Array<[string, unknown]> }) {
  return (
    <article className="result-card">
      <h3>{title}</h3>
      {rows.map(([key, value]) => (
        <p key={key}>
          <span>{key}</span>
          <strong>{String(value)}</strong>
        </p>
      ))}
    </article>
  );
}

export default App;
