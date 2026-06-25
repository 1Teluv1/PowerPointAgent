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
  const system = getMessageContent(detail, "system");
  const user = getMessageContent(detail, "user");
  const assistant = getMessageContent(detail, "assistant");

  return (
    <section className="panel" data-section="python-entry-review">
      <div className="panel-head">
        <div>
          <h2>Individual Python JSONL Review</h2>
          <p className="panel-note">
            생성 건별 JSONL 파일을 조회하고 SFT 메시지 구조와 Python 문법 검증 결과를 확인합니다.
          </p>
        </div>
        <span className="num">D5</span>
      </div>

      <div className="dataset-toolbar dataset-toolbar--actions">
        <button className="secondary" type="button" onClick={onRefresh} disabled={loading}>
          {loading ? "조회 중..." : "개별 파일 새로고침"}
        </button>
        <span className="hint">
          전체 {entries.length}개 · 정상 {entries.filter((entry) => entry.valid).length}개 · 오류{" "}
          {entries.filter((entry) => !entry.valid).length}개
        </span>
      </div>

      <div className="python-entry-review-grid">
        <div className="card python-entry-list-card">
          <h3>파일 목록</h3>
          <div className="execution-table-wrap">
            <table className="execution-table">
              <thead>
                <tr>
                  <th>검증</th>
                  <th>파일</th>
                  <th>Prompt</th>
                  <th>수정 시간</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.filename}
                    className={`execution-row execution-row--${entry.valid ? "done" : "error"}`}
                    onClick={() => onSelect(entry.filename)}
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") onSelect(entry.filename);
                    }}
                  >
                    <td>
                      <span className={`status-pill status-pill--${entry.valid ? "ok" : "error"}`}>
                        {entry.valid ? "정상" : "오류"}
                      </span>
                    </td>
                    <td>{entry.filename}</td>
                    <td className="execution-cell-truncate">{entry.user_prompt || "-"}</td>
                    <td>{formatUpdatedAt(entry.updated_at)}</td>
                  </tr>
                ))}
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
