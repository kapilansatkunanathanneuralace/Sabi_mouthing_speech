import type { DesktopPipeline, DictationHistoryEntry } from "./types/sidecar";

interface DictationHistoryProps {
  entries: DictationHistoryEntry[];
  onClear: () => void;
  onCopy: (text: string) => Promise<void>;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit"
  }).format(new Date(value));
}

function labelForPipeline(pipeline: DesktopPipeline | string): string {
  if (pipeline === "vsr") {
    return "VSR";
  }
  return pipeline.toUpperCase();
}

export function DictationHistory({ entries, onClear, onCopy }: DictationHistoryProps) {
  return (
    <section className="history-panel" aria-label="Dictation history">
      <div className="panel-heading">
        <div>
          <h2>Dictation history</h2>
          <p>Recent dictation results appear here even when paste is enabled.</p>
        </div>
        <button type="button" disabled={entries.length === 0} onClick={onClear}>
          Clear
        </button>
      </div>

      {entries.length === 0 ? (
        <p className="empty-state">
          No dictation results yet. Start dictation with the hotkey, then stop it to see the final
          transcript here.
        </p>
      ) : (
        <ol className="history-list">
          {entries.map((entry) => {
            const text = entry.textFinal || entry.textRaw || entry.error || "";
            return (
              <li key={entry.id} className={`history-item history-${entry.status}`}>
                <div className="history-meta">
                  <span>{formatTime(entry.createdAt)}</span>
                  <span>{labelForPipeline(entry.pipeline)}</span>
                  <span>{entry.decision ?? entry.status}</span>
                  {typeof entry.confidence === "number" ? (
                    <span>{Math.round(entry.confidence * 100)}% confidence</span>
                  ) : null}
                </div>
                <p className="history-text">{text || "(empty result)"}</p>
                {entry.textRaw && entry.textRaw !== entry.textFinal ? (
                  <details>
                    <summary>Raw transcript</summary>
                    <p>{entry.textRaw}</p>
                  </details>
                ) : null}
                <div className="actions compact">
                  <button type="button" disabled={!text} onClick={() => void onCopy(text)}>
                    Copy
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
