function defaultFormatTime(ts) {
  if (!ts) return "-";
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return "-";
  }
}

export default function ExecutionTimelineTable({ events, formatTime = defaultFormatTime, className = "" }) {
  if (!Array.isArray(events) || events.length === 0) {
    return <p className="hint">실행 이벤트 없음</p>;
  }

  return (
    <div className={`execution-table-wrap execution-timeline-wrap ${className}`.trim()}>
      <table className="execution-table">
        <thead>
          <tr>
            <th>시간</th>
            <th>Attempt</th>
            <th>종류</th>
            <th>Stage</th>
            <th>Target</th>
            <th>상태</th>
            <th>요약</th>
          </tr>
        </thead>
        <tbody>
          {events.map((item) => (
            <tr key={item.id} className={`execution-row execution-row--${item.status || "planned"}`}>
              <td>{formatTime(item.ts)}</td>
              <td>{item.attempt ?? "-"}</td>
              <td>{item.kind}</td>
              <td>{item.stage || "-"}</td>
              <td>{item.repairTarget || "-"}</td>
              <td>
                <span className={`status-pill status-pill--${item.status || "planned"}`}>
                  {item.status || "-"}
                </span>
              </td>
              <td className="execution-cell-detail" title={item.detail}>
                {item.detail}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
