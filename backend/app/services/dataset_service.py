from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List
import uuid

from app.models.schemas import DatasetFileStats
from app.models.schemas import PPTCodeBundle, PythonValidationResponse
from app.services.runner_service import run_ppt_code

DATASET_DIR = Path("data/datasets")
ASSET_DATASET_FILE = DATASET_DIR / "asset_lora.jsonl"
PYTHON_DATASET_FILE = DATASET_DIR / "python_lora.jsonl"
TOOL_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "tools"
ASSET_SYSTEM_PROMPT = "You generate only valid SVG code."
PYTHON_SYSTEM_PROMPT = "You generate only valid python-pptx code."


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.strip().split())


def build_key(user_prompt: str) -> str:
    normalized = normalize_prompt(user_prompt)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def ensure_dataset_dir() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)


def parse_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    rows: List[Dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_jsonl(path: Path, rows: List[Dict]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
    temp.replace(path)


def get_row_user_prompt(row: Dict) -> str:
    if isinstance(row.get("messages"), list):
        for item in row["messages"]:
            if isinstance(item, dict) and item.get("role") == "user":
                return normalize_prompt(str(item.get("content", "")))
    if isinstance(row.get("user_prompt"), str):
        return normalize_prompt(row["user_prompt"])
    return ""


def build_messages_row(user_prompt: str, answer_code: str, system_prompt: str) -> Dict:
    return {
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": normalize_prompt(user_prompt)},
            {"role": "assistant", "content": answer_code},
        ]
    }


def upsert_record(path: Path, user_prompt: str, answer_code: str, system_prompt: str) -> bool:
    records = parse_jsonl(path)
    target_prompt = normalize_prompt(user_prompt)
    next_row = build_messages_row(user_prompt, answer_code, system_prompt)

    replaced = False
    deduped: List[Dict] = []
    for row in records:
        if get_row_user_prompt(row) == target_prompt:
            if not replaced:
                deduped.append(next_row)
                replaced = True
            continue
        deduped.append(row)
    if not replaced:
        deduped.append(next_row)
    write_jsonl(path, deduped)
    return True


def upsert_pair(
    user_prompt: str,
    asset_code: str,
    python_code: str,
    asset_system_prompt: str = ASSET_SYSTEM_PROMPT,
    python_system_prompt: str = PYTHON_SYSTEM_PROMPT,
) -> str:
    ensure_dataset_dir()
    key = build_key(user_prompt)
    upsert_record(ASSET_DATASET_FILE, user_prompt, asset_code, asset_system_prompt)
    upsert_record(PYTHON_DATASET_FILE, user_prompt, python_code, python_system_prompt)
    return key


def get_stats() -> List[DatasetFileStats]:
    ensure_dataset_dir()
    stats: List[DatasetFileStats] = []
    for path in [ASSET_DATASET_FILE, PYTHON_DATASET_FILE]:
        records = parse_jsonl(path)
        size_bytes = path.stat().st_size if path.exists() else 0
        stats.append(
            DatasetFileStats(
                name=path.name,
                path=str(path),
                records=len(records),
                size_bytes=size_bytes,
                updated_at=None,
            )
        )
    return stats


def get_preview(dataset_type: str, limit: int, query: str) -> List[Dict]:
    path = ASSET_DATASET_FILE if dataset_type == "asset" else PYTHON_DATASET_FILE
    records = parse_jsonl(path)
    normalized_query = query.strip().lower()
    if normalized_query:
        records = [row for row in records if normalized_query in get_row_user_prompt(row).lower()]
    trimmed = records[-limit:] if limit > 0 else []
    return list(reversed(trimmed))


def validate_python_and_save_ppt(python_code: str) -> PythonValidationResponse:
    TOOL_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    run_dir = TOOL_ARTIFACT_ROOT / run_id
    result = run_ppt_code(run_dir, PPTCodeBundle(python_code=python_code, expected_outputs=["output.pptx"]))
    download_url = None
    if result.status == "ok":
        download_url = f"/tools/dataset/python-runs/{run_id}/pptx"
    return PythonValidationResponse(
        status=result.status,
        logs=result.logs,
        error_type=result.error_type,
        traceback=result.traceback,
        pptx_download_url=download_url,
    )
