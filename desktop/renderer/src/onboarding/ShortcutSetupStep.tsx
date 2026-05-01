import { useState } from "react";

import type { DesktopSettings, DesktopSettingsPatch } from "../types/sidecar";
import { nextStep } from "./steps";
import type { StepProps } from "./types";

interface Props extends StepProps {
  settings: DesktopSettings;
  testShortcut: (
    accelerator: string,
    timeoutMs?: number
  ) => Promise<{ ok: boolean; message: string }>;
  updateSettings: (patch: DesktopSettingsPatch) => Promise<DesktopSettings | undefined>;
  validateShortcut: (accelerator: string) => Promise<{ ok: boolean; message: string }>;
}

export function ShortcutSetupStep({
  goTo,
  platform,
  settings,
  testShortcut,
  updateSettings,
  validateShortcut
}: Props) {
  const [hotkey, setHotkey] = useState(settings.hotkey);
  const [message, setMessage] = useState(
    settings.shortcutVerified ? "Shortcut has already been confirmed." : ""
  );
  const [state, setState] = useState<"idle" | "validating" | "testing">("idle");
  const verified = settings.shortcutVerified && hotkey === settings.hotkey;

  async function validate() {
    setState("validating");
    setMessage("");
    try {
      const result = await validateShortcut(hotkey.trim());
      setMessage(result.message);
      if (result.ok) {
        await updateSettings({ hotkey: hotkey.trim(), shortcutVerified: false });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setState("idle");
    }
  }

  async function runTest() {
    setState("testing");
    setMessage(`Press ${hotkey} now.`);
    try {
      const result = await testShortcut(hotkey.trim(), 10000);
      setMessage(result.message);
      if (result.ok) {
        await updateSettings({ hotkey: hotkey.trim(), shortcutVerified: true });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setState("idle");
    }
  }

  return (
    <div className="wizard-step">
      <h2>Shortcut setup</h2>
      <p>
        Set the global shortcut Sabi should listen for. In push-to-talk mode, press it once to
        start listening and press it again to stop.
      </p>
      <label>
        Shortcut
        <input
          disabled={state !== "idle"}
          onChange={(event) => {
            setHotkey(event.target.value);
            setMessage("");
            if (settings.shortcutVerified) {
              void updateSettings({ shortcutVerified: false });
            }
          }}
          placeholder="Control+Alt+Space"
          value={hotkey}
        />
      </label>
      {message ? <p className={verified ? "success" : "error"}>{message}</p> : null}
      <div className="actions">
        <button type="button" disabled={state !== "idle"} onClick={() => void validate()}>
          {state === "validating" ? "Validating..." : "Validate shortcut"}
        </button>
        <button type="button" disabled={state !== "idle"} onClick={() => void runTest()}>
          {state === "testing" ? "Waiting for press..." : "Press to confirm"}
        </button>
        <button type="button" disabled={!verified} onClick={() => void goTo(nextStep("shortcut", platform))}>
          Continue
        </button>
      </div>
    </div>
  );
}
