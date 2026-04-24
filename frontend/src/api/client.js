const API_BASE = "http://localhost:8000";

export async function createJob(payload) {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("작업 생성 실패");
  return res.json();
}

export async function getJob(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error("작업 조회 실패");
  return res.json();
}

export async function getArtifacts(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/artifacts`);
  if (!res.ok) throw new Error("아티팩트 조회 실패");
  return res.json();
}
