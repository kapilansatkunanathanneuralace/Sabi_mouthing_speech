// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DictationHistory } from "../DictationHistory";
import type { DictationHistoryEntry } from "../types/sidecar";

const entry: DictationHistoryEntry = {
  id: "fused-1",
  createdAt: "2026-04-28T19:00:00.000Z",
  pipeline: "fused",
  utteranceId: 1,
  textRaw: "hello sabi",
  textFinal: "Hello Sabi.",
  confidence: 0.92,
  decision: "dry_run",
  status: "dry_run",
  error: null,
  payload: {
    pipeline: "fused",
    utterance_id: 1,
    text_raw: "hello sabi",
    text_final: "Hello Sabi.",
    confidence: 0.92,
    decision: "dry_run"
  }
};

describe("DictationHistory", () => {
  afterEach(() => cleanup());

  it("shows an empty state before the first utterance", () => {
    render(<DictationHistory entries={[]} onClear={vi.fn()} onCopy={vi.fn()} />);

    expect(screen.getByText(/no dictation results yet/i)).toBeTruthy();
  });

  it("renders dictation results and copies final text", async () => {
    const onCopy = vi.fn(async () => undefined);

    render(<DictationHistory entries={[entry]} onClear={vi.fn()} onCopy={onCopy} />);
    await userEvent.click(screen.getByRole("button", { name: /copy/i }));

    expect(screen.getByText("Hello Sabi.")).toBeTruthy();
    expect(screen.getByText("FUSED")).toBeTruthy();
    expect(onCopy).toHaveBeenCalledWith("Hello Sabi.");
  });
});
