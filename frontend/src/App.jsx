import { useMemo, useState } from "react";
import { createJob, getArtifacts, getJob } from "./api/client";
import RequestForm from "./components/RequestForm";
import PipelineStatusStepper from "./components/PipelineStatusStepper";
import AssetPreviewPanel from "./components/AssetPreviewPanel";
import CodeLogViewer from "./components/CodeLogViewer";
import ResultDownload from "./components/ResultDownload";
import DatasetToolPanel from "./components/DatasetToolPanel";

const TERMINAL_STATUSES = new Set(["completed", "failed"]);

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export default function App() {
  const [activeTab, setActiveTab] = useState("home");
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState(null);
  const [artifacts, setArtifacts] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(payload) {
    setLoading(true);
    setErrorMessage("");
    setArtifacts(null);
    try {
      const created = await createJob(payload);
      setJob(created);

      let latestJob = created;
      while (!TERMINAL_STATUSES.has(latestJob.status)) {
        await sleep(1500);
        latestJob = await getJob(created.job_id);
        setJob(latestJob);
      }

      if (latestJob.status === "completed") {
        const fetched = await getArtifacts(latestJob.job_id);
        setArtifacts(fetched);
      }
      setJob(latestJob);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "요청 처리에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  const badgeLabel = useMemo(() => {
    if (!job) return "Ready";
    if (job.status === "failed") return "Failed";
    if (job.status === "completed") return "Completed";
    return "Running";
  }, [job]);

  const badgeClassName = useMemo(() => {
    if (!job || job.status === "completed") return "badge";
    if (job.status === "failed") return "badge badge--failed";
    return "badge badge--running";
  }, [job]);

  return (
    <div className="app" data-component="AppLayout">
      <header className="header" data-component="AppHeader" data-section="header">
        <div>
          <p className="eyebrow">PPT Agent</p>
          <nav className="head-panel" aria-label="Primary">
            <button
              className={`head-panel__item ${activeTab === "home" ? "head-panel__item--active" : ""}`}
              type="button"
              onClick={() => setActiveTab("home")}
            >
              Home
            </button>
            <button className="head-panel__item" type="button">
              Setting
            </button>
            <button
              className={`head-panel__item ${activeTab === "tools" ? "head-panel__item--active" : ""}`}
              type="button"
              onClick={() => setActiveTab("tools")}
            >
              Tools
            </button>
          </nav>
          <h1>PPT Generation Agent</h1>
          <p className="subtitle">
            Plan, create visual assets, generate code, and export PPTX in one pipeline.
          </p>
        </div>
        <aside className="status-card" data-section="server-status">
          <span className={badgeClassName}>{badgeLabel}</span>
          <p className="job-id">
            Job ID: <strong>{job?.job_id ?? "-"}</strong>
          </p>
        </aside>
      </header>
      {activeTab === "home" ? (
        <main className="grid" data-component="MainGrid">
          <section className="panel" data-component="RequestFormSection" data-section="request-form">
            <div className="panel-head">
              <div>
                <h2>Request</h2>
                <p className="panel-note">Create a new PPT job.</p>
              </div>
              <span className="num">1</span>
            </div>
            <RequestForm onSubmit={handleSubmit} loading={loading} />
          </section>

          <section className="panel" data-component="PipelineStatusSection" data-section="pipeline-status">
            <div className="panel-head">
              <div>
                <h2>Pipeline</h2>
                <p className="panel-note">Live job status.</p>
              </div>
              <span className="num">2</span>
            </div>
            <PipelineStatusStepper status={job?.status} />
          </section>

          <section className="panel" data-component="ResultSection" data-section="result">
            <div className="panel-head">
              <div>
                <h2>Result</h2>
                <p className="panel-note">Assets, logs, and PPTX.</p>
              </div>
              <span className="num">3</span>
            </div>
            <div className="stack">
              <AssetPreviewPanel artifacts={artifacts} />
              <CodeLogViewer artifacts={artifacts} />
              <ResultDownload jobId={job?.job_id} status={job?.status} />
              {errorMessage && <div className="error">{errorMessage}</div>}
            </div>
          </section>
        </main>
      ) : (
        <main>
          <DatasetToolPanel />
        </main>
      )}
    </div>
  );
}
