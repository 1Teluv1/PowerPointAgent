export default function ResultDownload({ jobId, status }) {
  const canDownload = Boolean(jobId) && status === "completed";

  return (
    <article className="card">
      <h3>Download</h3>
      {canDownload ? (
        <a className="download" href={`http://localhost:8080/jobs/${jobId}/pptx`}>
          Download PPTX
        </a>
      ) : (
        <span className="download download--disabled">Ready when completed</span>
      )}
    </article>
  );
}
