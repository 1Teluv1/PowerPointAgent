import { useEffect, useMemo, useState } from "react";
import {
  consumeRawPromptPool,
  generateRawPromptPool,
  getDatasetPreview,
  getDatasetStats,
  getRawPromptPool
} from "../api/client";

const DATASET_FORM_STORAGE_KEY = "ppt-agent:tools:dataset-form";
const API_BASE = "http://localhost:8000";

const initialForm = {
  lmstudio_endpoint: "http://localhost:1234/v1/chat/completions",
  lmstudio_model: "local-model",
  prompt_count: 100,
  topic_seed: "diverse business PowerPoint presentation requests",
  count: 1,
  max_retries: 2
};

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DatasetToolPanel() {
  const [form, setForm] = useState(() => {
    try {
      const raw = localStorage.getItem(DATASET_FORM_STORAGE_KEY);
      if (!raw) return initialForm;
      const parsed = JSON.parse(raw);
      return {
        ...initialForm,
        ...parsed
      };
    } catch {
      return initialForm;
    }
  });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState([]);
  const [assetPreview, setAssetPreview] = useState([]);
  const [pythonPreview, setPythonPreview] = useState([]);
  const [query, setQuery] = useState("");
  const [pretty, setPretty] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pool, setPool] = useState(null);
  const [consumeResult, setConsumeResult] = useState(null);
  const [generatingPool, setGeneratingPool] = useState(false);
  const [consuming, setConsuming] = useState(false);

  async function refreshData(activeQuery = query) {
    setLoading(true);
    setError("");
    try {
      const statsRes = await getDatasetStats();
      const assetRes = await getDatasetPreview("asset", { limit: 10, query: activeQuery.trim() });
      const pythonRes = await getDatasetPreview("python", { limit: 10, query: activeQuery.trim() });
      const poolRes = await getRawPromptPool();
      setStats(statsRes.files ?? []);
      setAssetPreview(assetRes.records ?? []);
      setPythonPreview(pythonRes.records ?? []);
      setPool(poolRes);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "데이터 조회 실패");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshData("");
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(DATASET_FORM_STORAGE_KEY, JSON.stringify(form));
    } catch {
      // Ignore localStorage write failure (private mode/quota issues).
    }
  }, [form]);

  async function handleGeneratePool(event) {
    event.preventDefault();
    setGeneratingPool(true);
    setMessage("");
    setError("");
    setConsumeResult(null);
    try {
      const result = await generateRawPromptPool({
        lmstudio_endpoint: form.lmstudio_endpoint.trim(),
        lmstudio_model: form.lmstudio_model.trim(),
        prompt_count: Number(form.prompt_count),
        topic_seed: form.topic_seed.trim()
      });
      setPool(result);
      setMessage(`Raw Prompt 풀 생성 완료: ${result.summary?.total ?? 0}개`);
      await refreshData(query);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "Raw Prompt 풀 생성 실패");
    } finally {
      setGeneratingPool(false);
    }
  }

  async function handleConsumePool(event) {
    event.preventDefault();
    setSaving(true);
    setConsuming(true);
    setMessage("");
    setError("");
    setConsumeResult(null);
    try {
      const result = await consumeRawPromptPool({
        count: Number(form.count),
        lmstudio_endpoint: form.lmstudio_endpoint.trim(),
        lmstudio_model: form.lmstudio_model.trim(),
        max_retries: Number(form.max_retries)
      });
      setConsumeResult(result);
      setMessage(`Count 실행 완료: 성공 ${result.success}개, 실패 ${result.failed}개`);
      await refreshData(query);
    } catch (consumeError) {
      setError(consumeError instanceof Error ? consumeError.message : "Count 실행 실패");
    } finally {
      setSaving(false);
      setConsuming(false);
    }
  }

  const statsMap = useMemo(() => {
    const map = new Map();
    for (const item of stats) {
      map.set(item.name, item);
    }
    return map;
  }, [stats]);

  function renderRecordLine(record) {
    return pretty ? JSON.stringify(record, null, 2) : JSON.stringify(record);
  }

  const summary = pool?.summary ?? { total: 0, pending: 0, processing: 0, done: 0, failed: 0 };
  const previewItems = Array.isArray(pool?.items) ? pool.items.slice(0, 12) : [];

  return (
    <section className="tools-layout">
      <section className="panel" data-section="dataset-input">
        <div className="panel-head">
          <div>
            <h2>Raw Prompt Pool</h2>
            <p className="panel-note">LM Studio가 Raw Prompt 시스템 프롬프트와 100개 프롬프트 풀을 생성합니다.</p>
          </div>
          <span className="num">D1</span>
        </div>
        <form onSubmit={handleGeneratePool}>
          <div className="row">
            <div className="field">
            <label htmlFor="dataset-lmstudio-endpoint">LM Studio Endpoint *</label>
            <input
              id="dataset-lmstudio-endpoint"
              value={form.lmstudio_endpoint}
              required
              placeholder="http://localhost:1234/v1/chat/completions"
              onChange={(event) => setForm((prev) => ({ ...prev, lmstudio_endpoint: event.target.value }))}
            />
            </div>
            <div className="field">
            <label htmlFor="dataset-lmstudio-model">LM Studio Model *</label>
            <input
              id="dataset-lmstudio-model"
              value={form.lmstudio_model}
              required
              placeholder="local-model"
              onChange={(event) => setForm((prev) => ({ ...prev, lmstudio_model: event.target.value }))}
            />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label htmlFor="dataset-prompt-count">Prompt Pool Size *</label>
              <input
                id="dataset-prompt-count"
                value={String(form.prompt_count)}
                required
                placeholder="100"
                onChange={(event) => setForm((prev) => ({ ...prev, prompt_count: event.target.value }))}
              />
            </div>
            <div className="field">
              <label htmlFor="dataset-topic-seed">Topic Seed *</label>
              <input
                id="dataset-topic-seed"
                value={form.topic_seed}
                required
                placeholder="diverse business PowerPoint presentation requests"
                onChange={(event) => setForm((prev) => ({ ...prev, topic_seed: event.target.value }))}
              />
            </div>
          </div>
          <button disabled={generatingPool} className="primary" type="submit">
            {generatingPool ? "Raw Prompt 생성 중..." : "Raw Prompt 100개 생성"}
          </button>
          <p className="hint">
            생성 결과는 서버 메모리에 저장됩니다. 서버를 재시작하면 풀은 초기화됩니다.
          </p>
        </form>
        {pool?.system_prompt && (
          <div className="card">
            <h3>Raw Prompt System Prompt</h3>
            <pre>{pool.system_prompt}</pre>
          </div>
        )}
      </section>

      <section className="panel" data-section="dataset-consume">
        <div className="panel-head">
          <div>
            <h2>Count Runner</h2>
            <p className="panel-note">저장된 Raw Prompt 풀에서 Count개를 꺼내 1개씩 자동 처리합니다.</p>
          </div>
          <span className="num">D2</span>
        </div>
        <div className="dataset-stats">
          <div className="card">
            <h3>Total</h3>
            <p className="hint">{summary.total}</p>
          </div>
          <div className="card">
            <h3>Pending</h3>
            <p className="hint">{summary.pending}</p>
          </div>
          <div className="card">
            <h3>Done</h3>
            <p className="hint">{summary.done}</p>
          </div>
          <div className="card">
            <h3>Failed</h3>
            <p className="hint">{summary.failed}</p>
          </div>
        </div>
        <form onSubmit={handleConsumePool}>
          <div className="row">
            <div className="field">
              <label htmlFor="dataset-count">Count *</label>
              <input
                id="dataset-count"
                value={String(form.count)}
              required
                placeholder="1"
                onChange={(event) => setForm((prev) => ({ ...prev, count: event.target.value }))}
              />
            </div>
            <div className="field">
              <label htmlFor="dataset-max-retries">Max Retries *</label>
              <input
                id="dataset-max-retries"
                value={String(form.max_retries)}
                required
                placeholder="0~5"
                onChange={(event) => setForm((prev) => ({ ...prev, max_retries: event.target.value }))}
              />
            </div>
          </div>
          <button disabled={saving || summary.pending === 0} className="primary" type="submit">
            {consuming ? "Count 실행 중..." : "Count 만큼 실행"}
          </button>
          <p className="hint">
            각 항목은 LM Studio 생성, Python 실행 검증, 실패 재시도, JSONL 저장, PPT 썸네일 생성을 순차 수행합니다.
          </p>
        </form>
        {message && <div className="success">{message}</div>}
        {error && <div className="error">{error}</div>}
      </section>

      <section className="panel" data-section="dataset-results">
        <div className="panel-head">
          <div>
            <h2>Prompt Pool Status</h2>
            <p className="panel-note">최근 풀 항목과 Count 실행 결과, PPT 썸네일 미리보기</p>
          </div>
          <span className="num">D3</span>
        </div>
        <div className="dataset-toolbar">
          <button className="secondary" type="button" onClick={() => refreshData(query)} disabled={loading}>
            {loading ? "조회 중..." : "풀 상태 새로고침"}
          </button>
        </div>
        <div className="dataset-preview-grid">
          <div className="card">
            <h3>Prompt Pool Preview</h3>
            <pre>{previewItems.map((item) => `[${item.status}] ${item.index}. ${item.prompt}`).join("\n\n") || "데이터 없음"}</pre>
          </div>
          <div className="card">
            <h3>Consume Result</h3>
            <pre>{consumeResult ? JSON.stringify(consumeResult, null, 2) : "아직 실행 결과가 없습니다."}</pre>
          </div>
        </div>
        {consumeResult?.results?.map((result) => (
          <div className="card" key={result.prompt_id}>
            <h3>{result.status === "ok" ? "완료" : "실패"} · {result.prompt.slice(0, 90)}</h3>
            {result.pptx_download_url && (
              <a className="download" href={`${API_BASE}${result.pptx_download_url}`}>
                PPT 다운로드
              </a>
            )}
            {Array.isArray(result.thumbnail_urls) && result.thumbnail_urls.length > 0 && (
              <div className="thumbnail-grid">
                {result.thumbnail_urls.map((url) => (
                  <img key={url} src={`${API_BASE}${url}`} alt="PPT slide preview" />
                ))}
              </div>
            )}
            {result.traceback && <pre>{result.traceback}</pre>}
          </div>
        ))}
      </section>

      <section className="panel" data-section="dataset-status">
        <div className="panel-head">
          <div>
            <h2>Dataset Status</h2>
            <p className="panel-note">파일 크기와 레코드 개수, 미리보기</p>
          </div>
          <span className="num">D4</span>
        </div>
        <div className="dataset-toolbar">
          <input
            value={query}
            placeholder="prompt 검색"
            onChange={(event) => setQuery(event.target.value)}
          />
          <button className="secondary" type="button" onClick={() => refreshData(query)} disabled={loading}>
            {loading ? "조회 중..." : "조회"}
          </button>
          <button className="secondary" type="button" onClick={() => setPretty((prev) => !prev)}>
            {pretty ? "Compact" : "Pretty"}
          </button>
        </div>

        <div className="dataset-stats">
          <div className="card">
            <h3>asset_lora.jsonl</h3>
            <p className="hint">레코드: {statsMap.get("asset_lora.jsonl")?.records ?? 0}</p>
            <p className="hint">크기: {formatBytes(statsMap.get("asset_lora.jsonl")?.size_bytes ?? 0)}</p>
          </div>
          <div className="card">
            <h3>python_lora.jsonl</h3>
            <p className="hint">레코드: {statsMap.get("python_lora.jsonl")?.records ?? 0}</p>
            <p className="hint">크기: {formatBytes(statsMap.get("python_lora.jsonl")?.size_bytes ?? 0)}</p>
          </div>
        </div>

        <div className="dataset-preview-grid">
          <div className="card">
            <h3>Asset Preview (최근 10)</h3>
            <pre>{assetPreview.map((record) => renderRecordLine(record)).join("\n\n") || "데이터 없음"}</pre>
          </div>
          <div className="card">
            <h3>Python Preview (최근 10)</h3>
            <pre>{pythonPreview.map((record) => renderRecordLine(record)).join("\n\n") || "데이터 없음"}</pre>
          </div>
        </div>
      </section>
    </section>
  );
}
