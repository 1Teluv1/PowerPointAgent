import { useMemo, useState } from "react";
import { mergePythonDatasetEntries } from "../api/client";

function getMessageContent(detail, role) {
  const messages = detail?.row?.messages;
  if (!Array.isArray(messages)) return "";
  return messages.find((message) => message?.role === role)?.content ?? "";
}

function formatUpdatedAt(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function PythonDatasetEntryReview({ entries, detail, loading, onSelect, onRefresh }) {
  const [selectedFilenames, setSelectedFilenames] = useState(() => new Set());
  const [outputName, setOutputName] = useState("");
  const [merging, setMerging] = useState(false);
  const [mergeMessage, setMergeMessage] = useState("");
  const [mergeError, setMergeError] = useState("");

  const validEntries = useMemo(() => entries.filter((entry) => entry.valid), [entries]);
  const selectedValidCount = useMemo(
    () => entries.filter((entry) => entry.valid && selectedFilenames.has(entry.filename)).length,
    [entries, selectedFilenames]
  );
  const canMerge = selectedValidCount > 0 && outputName.trim().length > 0 && !merging;

  function toggleSelection(filename, checked) {
    setSelectedFilenames((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(filename);
      } else {
        next.delete(filename);
      }
      return next;
    });
  }

  function selectAll() {
    setSelectedFilenames(new Set(entries.map((entry) => entry.filename)));
  }

  function selectValidOnly() {
    setSelectedFilenames(new Set(validEntries.map((entry) => entry.filename)));
  }

  function clearSelection() {
    setSelectedFilenames(new Set());
  }

  async function handleMerge(event) {
    event.preventDefault();
    const filenames = entries
      .filter((entry) => entry.valid && selectedFilenames.has(entry.filename))
      .map((entry) => entry.filename);
    if (filenames.length === 0 || !outputName.trim()) {
      return;
    }

    setMerging(true);
    setMergeMessage("");
    setMergeError("");
    try {
      const result = await mergePythonDatasetEntries({
        filenames,
        output_name: outputName.trim()
      });
      const skippedCount = result.skipped_invalid?.length ?? 0;
      const missingCount = result.missing?.length ?? 0;
      let message = `${result.filename} 저장 완료 · ${result.record_count}개 레코드`;
      if (skippedCount > 0) {
        message += ` · 건너뜀(오류) ${skippedCount}개`;
      }
      if (missingCount > 0) {
        message += ` · 누락 ${missingCount}개`;
      }
      setMergeMessage(message);
      setSelectedFilenames(new Set());
      await onRefresh?.();
    } catch (mergeFailure) {
      setMergeError(mergeFailure instanceof Error ? mergeFailure.message : "병합 저장 실패");
    } finally {
      setMerging(false);
    }
  }

  const system = getMessageContent(detail, "system");
  const user = getMessageContent(detail, "user");
  const assistant = getMessageContent(detail, "assistant");

  return (
    <section className="panel" data-section="python-entry-review">
      <div className="panel-head">
        <div>
          <h2>Individual Python JSONL Review</h2>
          <p className="panel-note">
            생성 건별 JSONL 파일을 조회하고 SFT 메시지 구조와 Python 문법 검증 결과를 확인합니다. 선택한 정상
            파일을 하나의 JSONL로 병합 저장할 수 있습니다.
          </p>
        </div>
        <span className="num">D5</span>
      </div>

      <div className="dataset-toolbar dataset-toolbar--actions">
        <button className="secondary" type="button" onClick={onRefresh} disabled={loading}>
          {loading ? "조회 중..." : "개별 파일 새로고침"}
        </button>
        <span className="hint">
          전체 {entries.length}개 · 정상 {validEntries.length}개 · 오류 {entries.length - validEntries.length}개 ·
          선택 {selectedFilenames.size}개 (정상 {selectedValidCount}개)
        </span>
      </div>

      <form className="python-entry-export-toolbar card" onSubmit={handleMerge}>
        <div className="python-entry-export-toolbar__steps">
          <div className="field">
            <label>1. 데이터셋 선택</label>
            <div className="python-entry-export-toolbar__actions">
              <button className="secondary" type="button" onClick={selectAll} disabled={entries.length === 0}>
                전체 선택
              </button>
              <button className="secondary" type="button" onClick={selectValidOnly} disabled={validEntries.length === 0}>
                정상만 선택
              </button>
              <button className="secondary" type="button" onClick={clearSelection} disabled={selectedFilenames.size === 0}>
                선택 해제
              </button>
            </div>
          </div>
          <div className="field">
            <label htmlFor="python-entry-merge-name">2. 저장 이름</label>
            <input
              id="python-entry-merge-name"
              value={outputName}
              placeholder="merged_python_dataset.jsonl"
              onChange={(event) => setOutputName(event.target.value)}
            />
            <p className="hint">저장 위치: data/datasets/</p>
          </div>
          <div className="field python-entry-export-toolbar__save">
            <label>3. 저장</label>
            <button className="primary" type="submit" disabled={!canMerge}>
              {merging ? "병합 저장 중..." : "병합 저장"}
            </button>
          </div>
        </div>
        {mergeMessage && <div className="success">{mergeMessage}</div>}
        {mergeError && <div className="error">{mergeError}</div>}
      </form>

      <div className="python-entry-review-grid">
        <div className="card python-entry-list-card">
          <h3>파일 목록</h3>
          <div className="execution-table-wrap">
            <table className="execution-table">
              <thead>
                <tr>
                  <th className="python-entry-select-col">선택</th>
                  <th>검증</th>
                  <th>파일</th>
                  <th>Prompt</th>
                  <th>수정 시간</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const isSelected = selectedFilenames.has(entry.filename);
                  return (
                    <tr
                      key={entry.filename}
                      className={`execution-row execution-row--${entry.valid ? "done" : "error"}${isSelected ? " execution-row--selected" : ""}`}
                      onClick={() => onSelect(entry.filename)}
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") onSelect(entry.filename);
                      }}
                    >
                      <td className="python-entry-select-col">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={!entry.valid}
                          aria-label={`${entry.filename} 선택`}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => toggleSelection(entry.filename, event.target.checked)}
                        />
                      </td>
                      <td>
                        <span className={`status-pill status-pill--${entry.valid ? "ok" : "error"}`}>
                          {entry.valid ? "정상" : "오류"}
                        </span>
                      </td>
                      <td>{entry.filename}</td>
                      <td className="execution-cell-truncate">{entry.user_prompt || "-"}</td>
                      <td>{formatUpdatedAt(entry.updated_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {entries.length === 0 && <p className="hint">저장된 개별 JSONL 파일이 없습니다.</p>}
          </div>
        </div>

        <div className="card python-entry-detail-card">
          <div className="review-card-head">
            <h3>{detail?.filename ?? "파일 상세"}</h3>
            {detail && (
              <span className={`status-pill status-pill--${detail.valid ? "ok" : "error"}`}>
                {detail.valid ? "학습 형식 정상" : "검증 오류"}
              </span>
            )}
          </div>
          {!detail ? (
            <p className="hint">왼쪽 목록에서 파일을 선택하세요.</p>
          ) : (
            <>
              {!detail.valid && (
                <div className="error">
                  {(detail.errors ?? []).map((entryError) => (
                    <div key={entryError}>{entryError}</div>
                  ))}
                </div>
              )}
              <h4>System</h4>
              <pre>{system || "비어 있음"}</pre>
              <h4>User</h4>
              <pre>{user || "비어 있음"}</pre>
              <h4>Assistant Python</h4>
              <pre className="python-entry-code">{assistant || "비어 있음"}</pre>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
