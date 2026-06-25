import { useEffect, useRef } from "react";

export default function SavedPoolContentModal({ open, filename, content, onClose }) {
  const contentRef = useRef(null);

  useEffect(() => {
    if (open && contentRef.current) {
      contentRef.current.scrollTop = 0;
    }
  }, [open, filename, content]);

  if (!open) {
    return null;
  }

  return (
    <div className="log-modal-overlay" onClick={onClose} role="presentation">
      <div
        className="log-modal log-modal--wide"
        role="dialog"
        aria-modal="true"
        aria-label="저장된 Raw Prompt 풀"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="log-modal__header">
          <div>
            <h2>저장된 Raw Prompt 풀</h2>
            <p className="hint">{filename}</p>
          </div>
          <div className="log-modal__header-actions">
            <button className="secondary" type="button" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </header>

        <div className="log-modal__body">
          <pre className="log-modal__pane log-modal__pane--json" ref={contentRef}>
            {content || "{}"}
          </pre>
        </div>

        <footer className="log-modal__footer">
          <span className="hint">저장된 JSON 형식 그대로 표시</span>
          <button className="secondary" type="button" onClick={onClose}>
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}
