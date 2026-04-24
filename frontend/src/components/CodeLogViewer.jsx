export default function CodeLogViewer({ artifacts }) {
  const code = artifacts?.ppt_code_bundle?.python_code ?? "";
  const logs = artifacts?.runner_result?.logs ?? [];

  return (
    <article className="card">
      <h3>Logs</h3>
      <pre>{logs.length ? logs.join("\n") : "No logs yet."}</pre>
      <h3 style={{ marginTop: 12 }}>Code</h3>
      <pre>{code || "No generated code yet."}</pre>
    </article>
  );
}
