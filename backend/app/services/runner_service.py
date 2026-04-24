from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.models.schemas import PPTCodeBundle, RunnerResult


def run_ppt_code(job_dir: Path, code_bundle: PPTCodeBundle) -> RunnerResult:
    job_dir.mkdir(parents=True, exist_ok=True)
    script_path = job_dir / "generate_ppt.py"
    script_path.write_text(code_bundle.python_code, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(job_dir),
        capture_output=True,
        text=True,
        timeout=90,
    )

    logs = []
    if proc.stdout:
        logs.append(proc.stdout)
    if proc.stderr:
        logs.append(proc.stderr)

    if proc.returncode == 0:
        pptx_path = job_dir / "output.pptx"
        if pptx_path.exists():
            return RunnerResult(status="ok", logs=logs, pptx_path=str(pptx_path))
        return RunnerResult(status="error", logs=logs, error_type="MissingOutput", traceback="output.pptx not found")

    return RunnerResult(
        status="error",
        logs=logs,
        error_type="ExecutionError",
        traceback=proc.stderr or "Unknown execution error",
    )
