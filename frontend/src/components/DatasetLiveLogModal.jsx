import { useEffect, useRef } from "react";
import ConsumeResultCard from "./ConsumeResultCard";
import ExecutionTimelineTable from "./ExecutionTimelineTable";

export default function DatasetLiveLogModal({
  open,
  onClose,
  onReopen,
  isActive,
  activeTab,
  onTabChange,
  taggedLogLines,
  tokenStream,
  timelineEvents,
  reviewResults,
  apiBase,
  formatTime,
  showReasoning,
  onToggleReasoning,
  streamStatus,
  streamStage,
  streamAttempt,
  streamRepairTarget,
  streamEventCount,
  onClear
}) {
  const taggedRef = useRef(null);
  const tokenRef = useRef(null);
  const timelineRef = useRef(null);
  const reviewRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const ref =
      activeTab === "tokens"
        ? tokenRef
        : activeTab === "timeline"
          ? timelineRef
          : activeTab === "review"
            ? reviewRef
            : taggedRef;
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [open, activeTab, taggedLogLines, tokenStream, timelineEvents, reviewResults]);

  if (!open && !isActive) {
    return null;
  }

  const isWide = activeTab === "timeline" || activeTab === "review";
  const modalClass = isWide ? "log-modal log-modal--wide" : "log-modal";

  return (
    <>
      {!open && isActive && (
        <button className="log-fab" type="button" onClick={onReopen}>
          Live Log
        </button>
      )}

      {open && (
        <div className="log-modal-overlay" onClick={() => onClose(false)} role="presentation">
          <div
            className={modalClass}
            role="dialog"
            aria-modal="true"
            aria-label="Dataset Live Log"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="log-modal__header">
              <div>
                <h2>Dataset Live Log</h2>
                <p className="hint">
                  Status {streamStatus} · Stage {streamStage} · Attempt {streamAttempt} · Target{" "}
                  {streamRepairTarget}
                </p>
              </div>
              <div className="log-modal__header-actions">
                <button className="secondary" type="button" onClick={() => onClose(false)} aria-label="Minimize">
                  ─
                </button>
                <button className="secondary" type="button" onClick={() => onClose(true)} aria-label="Close">
                  ×
                </button>
              </div>
            </header>

            <div className="log-modal__tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "logs"}
                className={`log-modal__tab ${activeTab === "logs" ? "log-modal__tab--active" : ""}`}
                onClick={() => onTabChange("logs")}
              >
                Tagged Logs ({taggedLogLines.length})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "timeline"}
                className={`log-modal__tab ${activeTab === "timeline" ? "log-modal__tab--active" : ""}`}
                onClick={() => onTabChange("timeline")}
              >
                실행 타임라인 ({timelineEvents.length})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "review"}
                className={`log-modal__tab ${activeTab === "review" ? "log-modal__tab--active" : ""}`}
                onClick={() => onTabChange("review")}
              >
                Count 결과 ({reviewResults.length})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "tokens"}
                className={`log-modal__tab ${activeTab === "tokens" ? "log-modal__tab--active" : ""}`}
                onClick={() => onTabChange("tokens")}
              >
                LM Tokens
              </button>
            </div>

            <div className="log-modal__body">
              {activeTab === "logs" && (
                <pre className="log-modal__pane" ref={taggedRef}>
                  {taggedLogLines.length === 0 ? (
                    "데이터셋 작업이 시작되면 태그 형식 로그가 여기에 표시됩니다."
                  ) : (
                    taggedLogLines.map((line) => (
                      <div
                        key={line.id}
                        className={`log-line log-line--${line.tagPrefix} log-line--${line.level}`}
                      >
                        {line.text}
                      </div>
                    ))
                  )}
                </pre>
              )}
              {activeTab === "timeline" && (
                <div className="log-modal__pane log-modal__pane--timeline" ref={timelineRef}>
                  <ExecutionTimelineTable
                    events={timelineEvents}
                    formatTime={formatTime}
                    className="execution-timeline-wrap--modal"
                  />
                </div>
              )}
              {activeTab === "review" && (
                <div className="log-modal__pane log-modal__pane--review" ref={reviewRef}>
                  {reviewResults.length === 0 ? (
                    <p className="hint">아직 Count 결과가 없습니다. 실행이 끝나면 attempt 테이블이 표시됩니다.</p>
                  ) : (
                    reviewResults.map((result) => (
                      <ConsumeResultCard key={result.prompt_id} result={result} apiBase={apiBase} />
                    ))
                  )}
                </div>
              )}
              {activeTab === "tokens" && (
                <pre className="log-modal__pane log-modal__pane--tokens" ref={tokenRef}>
                  {tokenStream || "LM Studio 호출이 시작되면 실시간 토큰이 여기에 표시됩니다."}
                </pre>
              )}
            </div>

            <footer className="log-modal__footer">
              <span className="hint">Events {streamEventCount}</span>
              {activeTab === "tokens" && (
                <label className="log-modal__reasoning-toggle">
                  <input type="checkbox" checked={showReasoning} onChange={onToggleReasoning} />
                  reasoning 토큰 표시
                </label>
              )}
              <button className="secondary" type="button" onClick={onClear}>
                Clear
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
