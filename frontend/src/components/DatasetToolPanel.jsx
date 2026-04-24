import { useEffect, useMemo, useState } from "react";
import { getDatasetPreview, getDatasetStats, upsertDataset } from "../api/client";

const DATASET_FORM_STORAGE_KEY = "ppt-agent:tools:dataset-form";

const initialForm = {
  user_prompt: "",
  asset_system_prompt: "You generate only valid SVG code.",
  python_system_prompt: "You generate only valid python-pptx code.",
  asset_code: "",
  python_code: ""
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
  const [validateResult, setValidateResult] = useState(null);

  async function refreshData(activeQuery = query) {
    setLoading(true);
    setError("");
    try {
      const statsRes = await getDatasetStats();
      const assetRes = await getDatasetPreview("asset", { limit: 10, query: activeQuery.trim() });
      const pythonRes = await getDatasetPreview("python", { limit: 10, query: activeQuery.trim() });
      setStats(statsRes.files ?? []);
      setAssetPreview(assetRes.records ?? []);
      setPythonPreview(pythonRes.records ?? []);
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

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    setValidateResult(null);
    try {
      const payload = {
        user_prompt: form.user_prompt.trim(),
        asset_system_prompt: form.asset_system_prompt.trim(),
        python_system_prompt: form.python_system_prompt.trim(),
        asset_code: form.asset_code,
        python_code: form.python_code
      };
      const result = await upsertDataset(payload);
      setMessage(`저장 완료 (key: ${result.key})`);
      setValidateResult(result.validation ?? null);
      if (result.validation?.status === "error") {
        setError("데이터셋 저장은 완료되었지만 Python 코드 실행 검증은 실패했습니다.");
      }
      setForm(initialForm);
      await refreshData(query);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "저장 실패");
    } finally {
      setSaving(false);
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

  return (
    <section className="tools-layout">
      <section className="panel" data-section="dataset-input">
        <div className="panel-head">
          <div>
            <h2>Dataset Input</h2>
            <p className="panel-note">User는 자연어 프롬프트, Assistant는 정답 코드로 저장합니다.</p>
          </div>
          <span className="num">D1</span>
        </div>
        <form onSubmit={handleSave}>
          <div className="field">
            <label htmlFor="dataset-asset-system-prompt">Asset System Prompt *</label>
            <textarea
              id="dataset-asset-system-prompt"
              value={form.asset_system_prompt}
              required
              placeholder="Asset용 system 프롬프트"
              onChange={(event) => setForm((prev) => ({ ...prev, asset_system_prompt: event.target.value }))}
            />
          </div>
          <div className="field">
            <label htmlFor="dataset-python-system-prompt">Python System Prompt *</label>
            <textarea
              id="dataset-python-system-prompt"
              value={form.python_system_prompt}
              required
              placeholder="Python용 system 프롬프트"
              onChange={(event) => setForm((prev) => ({ ...prev, python_system_prompt: event.target.value }))}
            />
          </div>
          <div className="field">
            <label htmlFor="dataset-user-prompt">User Prompt *</label>
            <textarea
              id="dataset-user-prompt"
              value={form.user_prompt}
              required
              placeholder="사용자 자연어 요청을 입력하세요"
              onChange={(event) => setForm((prev) => ({ ...prev, user_prompt: event.target.value }))}
            />
          </div>
          <div className="field">
            <label htmlFor="dataset-asset-code">Asset Assistant Code *</label>
            <textarea
              id="dataset-asset-code"
              value={form.asset_code}
              required
              placeholder="assistant가 생성해야 할 Asset 코드 정답"
              onChange={(event) => setForm((prev) => ({ ...prev, asset_code: event.target.value }))}
            />
          </div>
          <div className="field">
            <label htmlFor="dataset-python-code">Python Assistant Code *</label>
            <textarea
              id="dataset-python-code"
              value={form.python_code}
              required
              placeholder="assistant가 생성해야 할 Python 코드 정답"
              onChange={(event) => setForm((prev) => ({ ...prev, python_code: event.target.value }))}
            />
          </div>
          <button disabled={saving} className="primary" type="submit">
            {saving ? "저장 중..." : "데이터셋 저장"}
          </button>
          <p className="hint">
            {saving ? "JSONL 저장 및 Python 실행 검증을 처리 중입니다." : "저장 시 Python 실행 검증과 PPT 저장을 자동 수행합니다."}
          </p>
        </form>
        {message && <div className="success">{message}</div>}
        {error && <div className="error">{error}</div>}
        {validateResult && (
          <div className="card">
            <h3>Python 검증 결과: {validateResult.status === "ok" ? "성공" : "실패"}</h3>
            {validateResult.pptx_download_url && (
              <a className="download" href={`http://localhost:8000${validateResult.pptx_download_url}`}>
                저장된 PPT 다운로드
              </a>
            )}
            {validateResult.traceback && <pre>{validateResult.traceback}</pre>}
            {Array.isArray(validateResult.logs) && validateResult.logs.length > 0 && (
              <pre>{validateResult.logs.join("\n\n")}</pre>
            )}
          </div>
        )}
      </section>

      <section className="panel" data-section="dataset-status">
        <div className="panel-head">
          <div>
            <h2>Dataset Status</h2>
            <p className="panel-note">파일 크기와 레코드 개수, 미리보기</p>
          </div>
          <span className="num">D2</span>
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
