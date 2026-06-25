import AttemptReviewTable from "./AttemptReviewTable";

export default function ConsumeResultCard({ result, apiBase }) {
  return (
    <div className="card consume-result-card">
      <div className="consume-result-head">
        <h3>
          <span className={`status-pill status-pill--${result.status === "ok" ? "ok" : "error"}`}>
            {result.status === "ok" ? "성공" : "실패"}
          </span>{" "}
          {result.prompt.slice(0, 120)}
        </h3>
        <p className="hint">prompt_id: {result.prompt_id}</p>
      </div>
      {result.pptx_download_url && (
        <a className="download" href={`${apiBase}${result.pptx_download_url}`}>
          PPT 다운로드
        </a>
      )}
      {Array.isArray(result.attempts) && result.attempts.length > 0 && (
        <div className="attempt-review-block">
          <h4>Attempt Review ({result.attempts.length})</h4>
          <AttemptReviewTable attempts={result.attempts} />
        </div>
      )}
      {Array.isArray(result.thumbnail_urls) && result.thumbnail_urls.length > 0 && (
        <div className="thumbnail-grid">
          {result.thumbnail_urls.map((url) => (
            <img key={url} src={`${apiBase}${url}`} alt="PPT slide preview" />
          ))}
        </div>
      )}
      {result.traceback && (
        <details className="traceback-details">
          <summary>Traceback 보기</summary>
          <pre>{result.traceback}</pre>
        </details>
      )}
    </div>
  );
}
