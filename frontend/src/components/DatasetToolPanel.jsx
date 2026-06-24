import { useEffect, useMemo, useRef, useState } from "react";
import {
  consumeRawPromptPool,
  generateRawPromptPool,
  getDatasetPreview,
  getDatasetStats,
  getRawPromptPool,
  getSavedRawPromptPools,
  loadSavedRawPromptPool,
  restoreRawPromptPool,
  subscribeLmStudioLiveAnswer
} from "../api/client";

const DATASET_FORM_STORAGE_KEY = "ppt-agent:tools:dataset-form";
const RAW_PROMPT_POOL_STORAGE_KEY = "ppt-agent:tools:raw-prompt-pool-snapshot";
const RUN_HISTORY_STORAGE_KEY = "ppt-agent:tools:run-history";
const API_BASE = "http://localhost:8080";
const MAX_RUN_HISTORY = 30;

function loadRunHistory() {
  try {
    const raw = localStorage.getItem(RUN_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function persistRunHistory(runs) {
  try {
    localStorage.setItem(RUN_HISTORY_STORAGE_KEY, JSON.stringify(runs.slice(0, MAX_RUN_HISTORY)));
  } catch {
    // ignore
  }
}

function formatTime(ts) {
  if (!ts) return "-";
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return "-";
  }
}

function nextEventId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function loadRawPromptPoolSnapshot() {
  try {
    const raw = localStorage.getItem(RAW_PROMPT_POOL_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.summary || typeof parsed.summary.total !== "number" || parsed.summary.total < 1) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function persistRawPromptPoolSnapshot(nextPool) {
  if (!nextPool?.summary || typeof nextPool.summary.total !== "number" || nextPool.summary.total < 1) {
    return;
  }
  try {
    localStorage.setItem(RAW_PROMPT_POOL_STORAGE_KEY, JSON.stringify(nextPool));
  } catch {
    // quota / private mode
  }
}

const initialForm = {
  lmstudio_endpoint: "http://localhost:1234/v1/chat/completions",
  lmstudio_model: "local-model",
  prompt_count: 100,
  topic_seed: "diverse business PowerPoint presentation requests",
  count: 1,
  max_retries: 0,
  dataset_system_prompt: ""
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
  const [pool, setPool] = useState(() => loadRawPromptPoolSnapshot());
  const [poolCacheActive, setPoolCacheActive] = useState(false);
  const [consumeResult, setConsumeResult] = useState(null);
  const [generatingPool, setGeneratingPool] = useState(false);
  const [consuming, setConsuming] = useState(false);
  const [savedPools, setSavedPools] = useState([]);
  const [loadingSavedPool, setLoadingSavedPool] = useState("");
  const [streamOutput, setStreamOutput] = useState("");
  const [streamError, setStreamError] = useState("");
  const [streamStatus, setStreamStatus] = useState("연결 대기");
  const [streamStage, setStreamStage] = useState("-");
  const [streamEventCount, setStreamEventCount] = useState(0);
  const [streamRepairTarget, setStreamRepairTarget] = useState("-");
  const [streamAttempt, setStreamAttempt] = useState("-");
  const [executionEvents, setExecutionEvents] = useState([]);
  const [runHistory, setRunHistory] = useState(() => loadRunHistory());
  const [selectedRunId, setSelectedRunId] = useState("current");
  const [showRawStream, setShowRawStream] = useState(true);
  const streamAbortRef = useRef(null);
  const streamOutputRef = useRef(null);
  const streamMetaRef = useRef({ attempt: "-", repairTarget: "-", stage: "-" });
  const executionEventsRef = useRef([]);

  function appendExecutionEvent(event) {
    setExecutionEvents((prev) => {
      const next = [...prev, event];
      executionEventsRef.current = next;
      return next;
    });
  }

  function clearExecutionEvents() {
    executionEventsRef.current = [];
    setExecutionEvents([]);
    setStreamAttempt("-");
    setStreamRepairTarget("-");
  }

  async function refreshSavedPools() {
    try {
      const res = await getSavedRawPromptPools();
      setSavedPools(res.files ?? []);
    } catch {
      setSavedPools([]);
    }
  }

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
      const serverTotal = poolRes?.summary?.total ?? 0;
      if (serverTotal > 0) {
        setPool(poolRes);
        persistRawPromptPoolSnapshot(poolRes);
        setPoolCacheActive(false);
      } else {
        const cached = loadRawPromptPoolSnapshot();
        if (cached) {
          setPool(cached);
          setPoolCacheActive(true);
        } else {
          setPool(poolRes);
          setPoolCacheActive(false);
        }
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "데이터 조회 실패");
    } finally {
      setLoading(false);
    }
    await refreshSavedPools();
  }

  useEffect(() => {
    refreshData("");
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    streamAbortRef.current = controller;

    subscribeLmStudioLiveAnswer({
      signal: controller.signal,
      onEvent: (event) => {
        if (event?.type === "ready") {
          setStreamStatus("연결됨");
          setStreamStage("live_answer");
          return;
        }

        setStreamEventCount((prev) => prev + 1);
        if (event?.stage) {
          setStreamStage(event.stage);
          streamMetaRef.current.stage = event.stage;
        }
        if (event?.type === "repair_plan") {
          if (event.attempt) {
            setStreamAttempt(String(event.attempt));
            streamMetaRef.current.attempt = String(event.attempt);
          }
          const target = event.repair_target ? String(event.repair_target) : "full";
          setStreamRepairTarget(target);
          streamMetaRef.current.repairTarget = target;
          appendExecutionEvent({
            id: nextEventId(),
            ts: Date.now(),
            kind: event.stage === "python_validation" ? "validation" : "repair_plan",
            attempt: event.attempt ?? null,
            stage: event.stage ?? "-",
            repairTarget: event.repair_target ?? null,
            failureKind: event.failure_kind ?? null,
            lockedFields: event.locked_fields ?? [],
            status: event.stage === "python_validation" ? "running" : "planned",
            detail: event.content || "repair plan"
          });
          setStreamOutput(
            (prev) =>
              `${prev}${prev ? "\n\n" : ""}>>> ${event.content || "repair plan"}\n`
          );
          return;
        }

        if (event?.type === "start") {
          setStreamStatus("생성 중");
          setStreamError("");
          const meta = streamMetaRef.current;
          appendExecutionEvent({
            id: nextEventId(),
            ts: Date.now(),
            kind: "lm_start",
            attempt: meta.attempt !== "-" ? Number(meta.attempt) : null,
            stage: event.stage || "lm_studio",
            repairTarget: meta.repairTarget !== "-" ? meta.repairTarget : null,
            status: "running",
            detail: `LM 호출 시작 · ${event.stage || "lm_studio"}`
          });
          setStreamOutput((prev) => `${prev}${prev ? "\n\n" : ""}--- ${event.stage || "lm_studio"} ---\n`);
          return;
        }
        if (event?.type === "delta") {
          setStreamOutput((prev) => prev + (event.content || ""));
          return;
        }
        if (event?.type === "end") {
          setStreamStatus("완료");
          const meta = streamMetaRef.current;
          appendExecutionEvent({
            id: nextEventId(),
            ts: Date.now(),
            kind: "lm_end",
            attempt: meta.attempt !== "-" ? Number(meta.attempt) : null,
            stage: meta.stage,
            repairTarget: meta.repairTarget !== "-" ? meta.repairTarget : null,
            status: "done",
            detail: `LM 호출 완료 · ${meta.stage}`
          });
          return;
        }
        if (event?.type === "error") {
          setStreamStatus("오류");
          setStreamError(event.content || "LM Studio Live Answer 오류");
          const meta = streamMetaRef.current;
          appendExecutionEvent({
            id: nextEventId(),
            ts: Date.now(),
            kind: "error",
            attempt: meta.attempt !== "-" ? Number(meta.attempt) : null,
            stage: meta.stage,
            repairTarget: meta.repairTarget !== "-" ? meta.repairTarget : null,
            status: "error",
            detail: event.content || "LM Studio 오류"
          });
        }
      }
    }).catch((subscribeError) => {
      if (subscribeError?.name !== "AbortError") {
        setStreamStatus("구독 실패");
        setStreamError(subscribeError instanceof Error ? subscribeError.message : "Live Answer 구독 실패");
      }
    });

    return () => {
      controller.abort();
      if (streamAbortRef.current === controller) {
        streamAbortRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (streamOutputRef.current) {
      streamOutputRef.current.scrollTop = streamOutputRef.current.scrollHeight;
    }
  }, [streamOutput]);

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
      persistRawPromptPoolSnapshot(result);
      setPoolCacheActive(false);
      const savedPath = result.saved_file ? ` · 저장: ${result.saved_file}` : "";
      setMessage(`Raw Prompt 풀 생성 완료: ${result.summary?.total ?? 0}개${savedPath}`);
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
    clearExecutionEvents();
    setSelectedRunId("current");
    const runId = String(Date.now());
    const runStartedAt = Date.now();
    appendExecutionEvent({
      id: nextEventId(),
      ts: runStartedAt,
      kind: "run_start",
      attempt: null,
      stage: "count_runner",
      repairTarget: null,
      status: "running",
      detail: `Count Runner 시작 · count=${Math.max(1, Number(form.count) || 1)}`
    });
    try {
      const serverPool = await getRawPromptPool();
      const emptySummary = { total: 0, pending: 0, processing: 0, done: 0, failed: 0 };
      let activeSummary = { ...emptySummary, ...serverPool.summary };
      const serverPending = activeSummary.pending ?? 0;
      const serverTotal = activeSummary.total ?? 0;

      // UI는 로컬 캐시로 pending이 보일 수 있으나 서버 메모리 풀이 비어 있으면 consume은 0건만 처리한다.
      // 복원 조건은 반드시 서버 상태(빈 풀) 기준으로 판단한다.
      if (serverPending === 0 && serverTotal === 0) {
        const cached = loadRawPromptPoolSnapshot();
        const cachedPending = Array.isArray(cached?.items)
          ? cached.items.filter((item) => item?.status === "pending" && String(item?.prompt || "").trim()).length
          : 0;
        if (cached && cachedPending > 0) {
          const restored = await restoreRawPromptPool({
            system_prompt: cached.system_prompt ?? null,
            items: cached.items.map((item) => ({
              prompt: String(item.prompt ?? "").trim(),
              status: item.status ?? "pending"
            }))
          });
          setPool(restored);
          persistRawPromptPoolSnapshot(restored);
          setPoolCacheActive(false);
          activeSummary = { ...emptySummary, ...restored.summary };
          setMessage(`로컬 Raw Prompt 풀을 서버로 복원했습니다. pending ${activeSummary.pending ?? 0}개`);
        } else {
          setPool(serverPool);
          if (cached) {
            setPool(cached);
            setPoolCacheActive(true);
          } else {
            setPoolCacheActive(false);
          }
        }
      } else {
        setPool(serverPool);
        if (serverTotal > 0) {
          persistRawPromptPoolSnapshot(serverPool);
          setPoolCacheActive(false);
        }
      }

      const requestedCount = Math.max(1, Number(form.count) || 1);
      const datasetSystemPrompt = typeof form.dataset_system_prompt === "string" ? form.dataset_system_prompt.trim() : "";
      const payload = {
        lmstudio_endpoint: form.lmstudio_endpoint.trim(),
        lmstudio_model: form.lmstudio_model.trim(),
        max_retries: Number(form.max_retries),
        ...(datasetSystemPrompt ? { system_prompt: datasetSystemPrompt } : {})
      };
      let aggregate = {
        processed: 0,
        success: 0,
        failed: 0,
        summary: activeSummary,
        results: []
      };

      setConsumeResult(aggregate);

      for (let index = 0; index < requestedCount; index += 1) {
        setMessage(`처리 중 ${index + 1}/${requestedCount} · 성공 ${aggregate.success} · 실패 ${aggregate.failed}`);

        const result = await consumeRawPromptPool({
          ...payload,
          count: 1
        });

        if (result.processed === 0) {
          break;
        }

        aggregate = {
          processed: aggregate.processed + (result.processed ?? 0),
          success: aggregate.success + (result.success ?? 0),
          failed: aggregate.failed + (result.failed ?? 0),
          summary: result.summary ?? aggregate.summary,
          results: [...aggregate.results, ...(result.results ?? [])]
        };
        setConsumeResult(aggregate);

        const poolRes = await getRawPromptPool();
        setPool(poolRes);
        if ((poolRes?.summary?.total ?? 0) > 0) {
          persistRawPromptPoolSnapshot(poolRes);
          setPoolCacheActive(false);
        }
      }

      setMessage(`Count 실행 완료: 성공 ${aggregate.success}개, 실패 ${aggregate.failed}개`);
      const finalTimeline = [
        ...executionEventsRef.current,
        {
          id: nextEventId(),
          ts: Date.now(),
          kind: "run_end",
          attempt: null,
          stage: "count_runner",
          repairTarget: null,
          status: aggregate.failed > 0 ? "error" : "done",
          detail: `Count 완료 · 성공 ${aggregate.success} · 실패 ${aggregate.failed}`
        }
      ];
      appendExecutionEvent(finalTimeline[finalTimeline.length - 1]);
      const historyEntry = {
        id: runId,
        startedAt: runStartedAt,
        endedAt: Date.now(),
        success: aggregate.success,
        failed: aggregate.failed,
        results: aggregate.results,
        timeline: finalTimeline,
        message: `성공 ${aggregate.success} · 실패 ${aggregate.failed}`
      };
      setRunHistory((prev) => {
        const next = [historyEntry, ...prev].slice(0, MAX_RUN_HISTORY);
        persistRunHistory(next);
        return next;
      });
      await refreshData(query);
    } catch (consumeError) {
      setError(consumeError instanceof Error ? consumeError.message : "Count 실행 실패");
    } finally {
      setSaving(false);
      setConsuming(false);
    }
  }

  async function handleLoadSavedPool(filename) {
    setLoadingSavedPool(filename);
    setMessage("");
    setError("");
    try {
      const result = await loadSavedRawPromptPool(filename);
      setPool(result);
      persistRawPromptPoolSnapshot(result);
      setPoolCacheActive(false);
      setMessage(`저장된 풀 불러오기 완료: ${result.summary?.total ?? 0}개 (${filename})`);
      await refreshData(query);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "저장된 Raw Prompt 풀 불러오기 실패");
    } finally {
      setLoadingSavedPool("");
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

  function renderAttemptsTable(attempts) {
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
              <tr key={`${item.attempt}-${item.stage}-${item.status}`} className={`execution-row execution-row--${item.status}`}>
                <td>{item.attempt}</td>
                <td>{item.stage}</td>
                <td><span className={`status-pill status-pill--${item.status}`}>{item.status}</span></td>
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

  function renderExecutionTimeline(events) {
    if (!Array.isArray(events) || events.length === 0) {
      return <p className="hint">실행 이벤트 없음</p>;
    }
    return (
      <div className="execution-table-wrap execution-timeline-wrap">
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
                <td><span className={`status-pill status-pill--${item.status || "planned"}`}>{item.status || "-"}</span></td>
                <td className="execution-cell-detail" title={item.detail}>{item.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderConsumeResultCard(result) {
    return (
      <div className="card consume-result-card" key={result.prompt_id}>
        <div className="consume-result-head">
          <h3>
            <span className={`status-pill status-pill--${result.status === "ok" ? "ok" : "error"}`}>
              {result.status === "ok" ? "성공" : "실패"}
            </span>
            {" "}
            {result.prompt.slice(0, 120)}
          </h3>
          <p className="hint">prompt_id: {result.prompt_id}</p>
        </div>
        {result.pptx_download_url && (
          <a className="download" href={`${API_BASE}${result.pptx_download_url}`}>
            PPT 다운로드
          </a>
        )}
        {Array.isArray(result.attempts) && result.attempts.length > 0 && (
          <div className="attempt-review-block">
            <h4>Attempt Review ({result.attempts.length})</h4>
            {renderAttemptsTable(result.attempts)}
          </div>
        )}
        {Array.isArray(result.thumbnail_urls) && result.thumbnail_urls.length > 0 && (
          <div className="thumbnail-grid">
            {result.thumbnail_urls.map((url) => (
              <img key={url} src={`${API_BASE}${url}`} alt="PPT slide preview" />
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

  const summary = pool?.summary ?? { total: 0, pending: 0, processing: 0, done: 0, failed: 0 };
  const poolItems = Array.isArray(pool?.items) ? pool.items : [];
  const rawPoolSizeNumber = Number(form.prompt_count);
  const poolSizeLabel =
    Number.isFinite(rawPoolSizeNumber) && rawPoolSizeNumber >= 1
      ? Math.min(200, Math.floor(rawPoolSizeNumber))
      : 100;

  const selectedRun = useMemo(() => {
    if (selectedRunId === "current") return null;
    return runHistory.find((run) => run.id === selectedRunId) ?? null;
  }, [selectedRunId, runHistory]);

  const timelineEvents =
    selectedRunId === "current" ? executionEvents : selectedRun?.timeline ?? [];

  const reviewResults =
    selectedRunId === "current"
      ? consumeResult?.results ?? []
      : selectedRun?.results ?? [];

  return (
    <section className="tools-layout">
      <section className="panel" data-section="dataset-input">
        <div className="panel-head">
          <div>
            <h2>Raw Prompt Pool</h2>
            <p className="panel-note">
              LM Studio가 Raw Prompt 시스템 프롬프트와 {poolSizeLabel}개 프롬프트 풀을 생성합니다. (서버는 최대 20개씩
              나누어 요청합니다.) 생성된 풀은 브라우저 로컬 스토리지와 서버 JSON 파일(
              <code>data/datasets/raw_prompt_pools/raw_prompts_YYYY-MM-DD.json</code>)에 저장됩니다.
            </p>
            {poolCacheActive && (
              <p className="hint">
                현재 표시는 로컬에 저장된 풀입니다. 서버 메모리 풀이 비어 있으면 Count Runner가 처리할 항목이 없을 수
                있습니다. 풀을 다시 생성하면 서버와 동기화됩니다.
              </p>
            )}
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
            {generatingPool ? "Raw Prompt 생성 중..." : `Raw Prompt ${poolSizeLabel}개 생성`}
          </button>
          <p className="hint">
            생성 결과는 서버 메모리와 날짜 기준 JSON 파일에 저장됩니다. 서버를 재시작하면 메모리 풀은 초기화되지만, 아래
            저장 목록에서 JSON 파일을 불러와 다시 사용할 수 있습니다.
          </p>
        </form>
        {savedPools.length > 0 && (
          <div className="card">
            <h3>저장된 Raw Prompt 풀</h3>
            <ul className="saved-pool-list">
              {savedPools.map((file) => (
                <li key={file.filename} className="saved-pool-item">
                  <div>
                    <strong>{file.filename}</strong>
                    <p className="hint">
                      {file.prompt_count}개
                      {file.topic_seed ? ` · ${file.topic_seed.slice(0, 60)}` : ""}
                      {file.saved_at ? ` · ${file.saved_at}` : ""}
                    </p>
                  </div>
                  <button
                    className="secondary"
                    type="button"
                    disabled={Boolean(loadingSavedPool)}
                    onClick={() => handleLoadSavedPool(file.filename)}
                  >
                    {loadingSavedPool === file.filename ? "불러오는 중..." : "불러오기"}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
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
                placeholder="0 = unlimited"
                onChange={(event) => setForm((prev) => ({ ...prev, max_retries: event.target.value }))}
              />
              <p className="hint">0이면 성공할 때까지 무제한 재시도합니다. 1 이상이면 해당 횟수만큼 repair를 시도합니다.</p>
            </div>
          </div>
          <div className="field">
            <label htmlFor="dataset-consume-system-prompt">데이터셋 생성 시스템 프롬프트 (선택)</label>
            <textarea
              id="dataset-consume-system-prompt"
              rows={6}
              placeholder="비워 두면 서버 기본(Raw Prompt 풀 생성 시 사용된 시스템 프롬프트와 동일 계열)이 적용됩니다. LM Studio markdown 생성에 사용됩니다."
              value={form.dataset_system_prompt ?? ""}
              onChange={(event) => setForm((prev) => ({ ...prev, dataset_system_prompt: event.target.value }))}
            />
            <p className="hint">
              입력 내용은 브라우저 로컬 스토리지에 자동 저장되어 다음 실행 시에도 유지됩니다.
            </p>
          </div>
          <button disabled={saving || (summary.pending === 0 && !poolCacheActive)} className="primary" type="submit">
            {consuming ? "Count 실행 중..." : "Count 만큼 실행"}
          </button>
          <p className="hint">
            각 항목은 LM Studio 생성, Python 실행 검증, 실패 시 필드 단위 재시도(에러·세션 메모리 포함), JSONL 저장, PPT 썸네일 생성을 순차 수행합니다.
          </p>
        </form>
        {message && selectedRunId === "current" && <div className="success">{message}</div>}
        {error && <div className="error">{error}</div>}
      </section>

      <section className="panel panel--review" data-section="execution-review">
        <div className="panel-head">
          <div>
            <h2>Execution & Review</h2>
            <p className="panel-note">
              현재 실행과 이전 실행의 타임라인·attempt·결과를 한곳에서 확인합니다. Count 실행 중에도 실시간으로
              업데이트됩니다.
            </p>
          </div>
          <span className="num">R</span>
        </div>

        <div className="review-toolbar">
          <label htmlFor="run-history-select">실행 선택</label>
          <select
            id="run-history-select"
            value={selectedRunId}
            onChange={(event) => setSelectedRunId(event.target.value)}
          >
            <option value="current">현재 실행 {consuming ? "(진행 중)" : ""}</option>
            {runHistory.map((run) => (
              <option key={run.id} value={run.id}>
                {formatTime(run.startedAt)} · {run.message || `성공 ${run.success}`}
              </option>
            ))}
          </select>
          <button className="secondary" type="button" onClick={() => { clearExecutionEvents(); setStreamOutput(""); }}>
            현재 타임라인 초기화
          </button>
        </div>

        <div className="run-status-banner">
          <div>
            <strong>Live</strong> · Status {streamStatus} · Stage {streamStage} · Attempt {streamAttempt} · Target{" "}
            {streamRepairTarget}
          </div>
          {consuming && <span className="status-pill status-pill--running">Count 실행 중</span>}
          {message && <p className="hint">{message}</p>}
        </div>

        <div className="review-grid">
          <div className="card review-card">
            <h3>실행 타임라인 ({timelineEvents.length})</h3>
            {renderExecutionTimeline(timelineEvents)}
          </div>
          <div className="card review-card">
            <h3>Count 결과 & Attempt Review</h3>
            {reviewResults.length === 0 ? (
              <p className="hint">아직 Count 결과가 없습니다. 실행이 끝나면 attempt 테이블이 표시됩니다.</p>
            ) : (
              reviewResults.map((result) => renderConsumeResultCard(result))
            )}
          </div>
        </div>
      </section>

      <section className="panel" data-section="lmstudio-stream">
        <div className="panel-head">
          <div>
            <h2>LM Studio Live Answer</h2>
            <p className="panel-note">
              Raw Prompt 생성, Count Runner, 재시도 등 모든 LM Studio 호출의 토큰 델타를 자동으로 표시합니다.
            </p>
          </div>
          <span className="num">S</span>
        </div>
        <div className="stream-meta-grid">
          <div className="card">
            <h3>Status</h3>
            <p className="hint">{streamStatus}</p>
          </div>
          <div className="card">
            <h3>Stage</h3>
            <p className="hint">{streamStage}</p>
          </div>
          <div className="card">
            <h3>Events</h3>
            <p className="hint">{streamEventCount}</p>
          </div>
          <div className="card">
            <h3>Attempt</h3>
            <p className="hint">{streamAttempt}</p>
          </div>
          <div className="card">
            <h3>Repair Target</h3>
            <p className="hint">{streamRepairTarget}</p>
          </div>
        </div>
        <div className="dataset-toolbar dataset-toolbar--actions">
          <button className="secondary" type="button" onClick={() => setShowRawStream((prev) => !prev)}>
            {showRawStream ? "Raw Stream 숨기기" : "Raw Stream 보기"}
          </button>
          <button className="secondary" type="button" onClick={() => setStreamOutput("")}>
            Clear
          </button>
        </div>
        {streamError && <div className="error">{streamError}</div>}
        {showRawStream && (
          <div className="card stream-output-card">
            <h3>Live Answer (Raw LM Tokens)</h3>
            <pre className="stream-output" ref={streamOutputRef}>
              {streamOutput || "LM Studio 호출이 시작되면 여기에 실시간 답변이 표시됩니다."}
            </pre>
          </div>
        )}
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
          <div className="card pool-table-card">
            <h3>Prompt Pool 전체 ({poolItems.length})</h3>
            <div className="execution-table-wrap">
              <table className="execution-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Status</th>
                    <th>Prompt</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {poolItems.map((item) => (
                    <tr key={item.id} className={`execution-row execution-row--${item.status}`}>
                      <td>{item.index}</td>
                      <td><span className={`status-pill status-pill--${item.status === "done" ? "ok" : item.status}`}>{item.status}</span></td>
                      <td className="execution-cell-detail">{item.prompt}</td>
                      <td className="execution-cell-truncate">{item.error_type || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {poolItems.length === 0 && <p className="hint">풀 데이터 없음</p>}
            </div>
          </div>
          <div className="card">
            <h3>Consume Aggregate</h3>
            <pre>{consumeResult ? JSON.stringify(consumeResult, null, 2) : "아직 실행 결과가 없습니다."}</pre>
          </div>
        </div>
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
