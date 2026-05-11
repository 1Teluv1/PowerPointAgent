from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import shutil

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
        # Allow user code to save PPTX with custom filename.
        generated = sorted(job_dir.glob("*.pptx"), key=lambda path: path.stat().st_mtime, reverse=True)
        if generated:
            source = generated[0]
            if source != pptx_path:
                shutil.copy2(source, pptx_path)
            return RunnerResult(status="ok", logs=logs, pptx_path=str(pptx_path))
        return RunnerResult(
            status="error",
            logs=logs,
            error_type="MissingOutput",
            traceback="output.pptx not found (no .pptx file generated in working directory)",
        )

    err_parts = [part for part in (proc.stderr, proc.stdout) if part and str(part).strip()]
    traceback_text = "\n\n".join(err_parts) if err_parts else "Unknown execution error"

    return RunnerResult(
        status="error",
        logs=logs,
        error_type="ExecutionError",
        traceback=traceback_text,
    )
