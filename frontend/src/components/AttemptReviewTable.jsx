export default function AttemptReviewTable({ attempts }) {
  if (!Array.isArray(attempts) || attempts.length === 0) {
    return <p className="hint">attempt 기록 없음</p>;
  }

  return (
    <div className="execution-table-wrap">
      <table className="execution-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Stage</th>
            <th>Status</th>
            <th>Target</th>
            <th>Failure</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map((item) => (
            <tr
              key={`${item.attempt}-${item.stage}-${item.status}`}
              className={`execution-row execution-row--${item.status}`}
            >
              <td>{item.attempt}</td>
              <td>{item.stage}</td>
              <td>
                <span className={`status-pill status-pill--${item.status}`}>{item.status}</span>
              </td>
              <td>{item.repair_target || "-"}</td>
              <td>{item.failure_kind || "-"}</td>
              <td className="execution-cell-truncate" title={item.traceback || item.error_type || ""}>
                {item.error_type || (item.status === "ok" ? "ok" : "-")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
