from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

from app.models.schemas import (
    DatasetAutoAttempt,
    DatasetAutoGenerateRequest,
    DatasetAutoGenerateResponse,
    DatasetFileStats,
    RawPromptPoolConsumeItemResult,
    RawPromptPoolConsumeRequest,
    RawPromptPoolConsumeResponse,
    RawPromptPoolGenerateRequest,
    RawPromptPoolRestoreItem,
    RawPromptPoolRestoreRequest,
    RawPromptPoolItem,
    RawPromptPoolResponse,
    RawPromptPoolSummary,
)
from app.models.schemas import PPTCodeBundle, PythonValidationResponse
from app.services.dataset_repair import (
    assemble_dataset_markdown,
    build_repair_context,
    classify_dataset_failure,
    execute_field_repair,
    missing_repair_target,
)
from app.services.dataset_repair_session import (
    clear_repair_session,
    format_session_memory_for_prompt,
    load_repair_session,
    merge_repair_memory_addons,
    record_repair_session_error,
)
from app.services.lm_studio_service import (
    LMStudioError,
    generate_markdown_sample,
    generate_raw_prompt_list,
    generate_raw_prompt_system_prompt,
    publish_live_answer_event,
)
from app.services.ppt_preview_service import export_pptx_thumbnails
from app.services.pptx_error_memory import format_error_memory_for_prompt, record_error
from app.services.runner_service import run_ppt_code

DATASET_DIR = Path("data/datasets")
RAW_PROMPT_POOL_DIR = DATASET_DIR / "raw_prompt_pools"
ASSET_DATASET_FILE = DATASET_DIR / "asset_lora.jsonl"
PYTHON_DATASET_FILE = DATASET_DIR / "python_lora.jsonl"
TOOL_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "tools"
ASSET_SYSTEM_PROMPT = "You generate only valid SVG code."
PYTHON_SYSTEM_PROMPT = (
    "You generate only valid python-pptx code. "
    "Use XL_CHART_TYPE (not ChartType) for charts; guard slide.shapes.title for None; "
    "use exact # User Prompt / # Thinking / # Assistant sections with ```text and ```python fences."
)
RAW_PROMPT_POOL: List[Dict] = []

# LM Studio 한 번에 요청할 Raw Prompt 개수 상한 (토큰·안정성)
RAW_PROMPT_LIST_CHUNK_SIZE = 20
RAW_PROMPT_SYSTEM_PROMPT: Optional[str] = None


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.strip().split())


def build_key(user_prompt: str) -> str:
    normalized = normalize_prompt(user_prompt)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def ensure_dataset_dir() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)


def ensure_raw_prompt_pool_dir() -> None:
    ensure_dataset_dir()
    RAW_PROMPT_POOL_DIR.mkdir(parents=True, exist_ok=True)


def _build_raw_prompt_pool_filename() -> str:
    today = datetime.now().date().isoformat()
    base = f"raw_prompts_{today}.json"
    ensure_raw_prompt_pool_dir()
    if not (RAW_PROMPT_POOL_DIR / base).exists():
        return base
    seq = 2
    while True:
        name = f"raw_prompts_{today}_{seq}.json"
        if not (RAW_PROMPT_POOL_DIR / name).exists():
            return name
        seq += 1


def save_raw_prompt_pool_to_file(*, topic_seed: str, prompt_count: int) -> str:
    ensure_raw_prompt_pool_dir()
    filename = _build_raw_prompt_pool_filename()
    path = RAW_PROMPT_POOL_DIR / filename
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "topic_seed": topic_seed,
        "prompt_count": prompt_count,
        "system_prompt": RAW_PROMPT_SYSTEM_PROMPT,
        "summary": _pool_summary().model_dump(),
        "items": [
            {
                "index": item["index"],
                "prompt": item["prompt"],
                "status": item.get("status", "pending"),
            }
            for item in RAW_PROMPT_POOL
        ],
    }
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return str(path)


def list_saved_raw_prompt_pools() -> List[Dict]:
    ensure_raw_prompt_pool_dir()
    files = sorted(
        RAW_PROMPT_POOL_DIR.glob("raw_prompts_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    result: List[Dict] = []
    for path in files:
        saved_at: Optional[str] = None
        topic_seed: Optional[str] = None
        item_count = 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                saved_at = data.get("saved_at")
                topic_seed = data.get("topic_seed")
                items = data.get("items", [])
                item_count = len(items) if isinstance(items, list) else 0
        except (json.JSONDecodeError, OSError):
            pass
        result.append(
            {
                "filename": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "saved_at": saved_at,
                "prompt_count": item_count,
                "topic_seed": topic_seed,
            }
        )
    return result


def load_raw_prompt_pool_from_file(filename: str) -> RawPromptPoolResponse:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.startswith("raw_prompts_") or not safe_name.endswith(".json"):
        raise ValueError("Invalid raw prompt pool filename")
    path = RAW_PROMPT_POOL_DIR / safe_name
    if not path.exists():
        raise FileNotFoundError(f"Saved raw prompt pool not found: {safe_name}")

    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list) or len(items) < 1:
        raise ValueError("Saved raw prompt pool has no items")

    restore_items: List[RawPromptPoolRestoreItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt", "")).strip()
        if not prompt:
            continue
        status = item.get("status", "pending")
        if status not in {"pending", "processing", "done", "failed"}:
            status = "pending"
        restore_items.append(RawPromptPoolRestoreItem(prompt=prompt, status=status))

    if not restore_items:
        raise ValueError("Saved raw prompt pool has no valid prompts")

    system_prompt = data.get("system_prompt") if isinstance(data, dict) else None
    return restore_raw_prompt_pool(
        RawPromptPoolRestoreRequest(
            system_prompt=system_prompt.strip() if isinstance(system_prompt, str) and system_prompt.strip() else None,
            items=restore_items,
        )
    )


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


def _run_python_and_save_ppt(python_code: str) -> Tuple[PythonValidationResponse, str, Path]:
    TOOL_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    run_dir = TOOL_ARTIFACT_ROOT / run_id
    result = run_ppt_code(run_dir, PPTCodeBundle(python_code=python_code, expected_outputs=["output.pptx"]))
    download_url = None
    if result.status == "ok":
        download_url = f"/tools/dataset/python-runs/{run_id}/pptx"
    response = PythonValidationResponse(
        status=result.status,
        logs=result.logs,
        error_type=result.error_type,
        traceback=result.traceback,
        pptx_download_url=download_url,
    )
    return response, run_id, run_dir / "output.pptx"


def validate_python_and_save_ppt(python_code: str) -> PythonValidationResponse:
    response, _, _ = _run_python_and_save_ppt(python_code)
    return response


def _extract_section_block(markdown: str, section_title: str, block_lang: str) -> str:
    pattern = (
        r"(?:^|\n)\#\s*"
        + re.escape(section_title)
        + r"\s*\n\s*```"
        + re.escape(block_lang)
        + r"\s*\n(.*?)\n```"
    )
    match = re.search(pattern, markdown, flags=re.DOTALL)
    if not match:
        raise ValueError(f"섹션 파싱 실패: {section_title}")
    return match.group(1).strip()


def _try_extract_section_block(markdown: str, section_title: str, block_lang: str) -> Optional[str]:
    try:
        return _extract_section_block(markdown, section_title, block_lang)
    except ValueError:
        return None


def parse_markdown_dataset(markdown: str, *, raw_prompt: Optional[str] = None) -> Dict[str, str]:
    user_prompt = _try_extract_section_block(markdown, "User Prompt", "text")
    if not user_prompt:
        user_prompt = (raw_prompt or "").strip()
    if not user_prompt:
        raise ValueError("섹션 파싱 실패: User Prompt")
    thinking = _try_extract_section_block(markdown, "Thinking", "text") or ""
    assistant_python = _try_extract_section_block(markdown, "Assistant", "python") or ""
    return {
        "user_prompt": user_prompt,
        "thinking": thinking,
        "assistant_python": assistant_python,
    }


def _assemble_dataset_markdown(fixed_user_prompt: str, fixed_thinking: str, assistant_python: str) -> str:
    return assemble_dataset_markdown(fixed_user_prompt, fixed_thinking, assistant_python)


def _parse_markdown_with_raw_prompt(
    *,
    markdown: str,
    raw_prompt: str,
    endpoint: str,
    model: str,
    error_memory_addon: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    parsed = parse_markdown_dataset(markdown, raw_prompt=raw_prompt)
    raw_user_prompt = raw_prompt.strip()
    normalized_markdown = _assemble_dataset_markdown(
        raw_user_prompt,
        parsed["thinking"],
        parsed["assistant_python"],
    )
    return normalized_markdown, parse_markdown_dataset(normalized_markdown, raw_prompt=raw_prompt)


def build_data_messages_row(system_prompt: str, user_prompt: str, assistant_markdown: str) -> Dict:
    return {
        "data": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": assistant_markdown},
            ]
        }
    }


def _pool_summary() -> RawPromptPoolSummary:
    counts = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
    for item in RAW_PROMPT_POOL:
        status = str(item.get("status", "pending"))
        if status in counts:
            counts[status] += 1
    return RawPromptPoolSummary(
        total=len(RAW_PROMPT_POOL),
        pending=counts["pending"],
        processing=counts["processing"],
        done=counts["done"],
        failed=counts["failed"],
    )


def _pool_item_model(item: Dict) -> RawPromptPoolItem:
    return RawPromptPoolItem(
        id=str(item["id"]),
        index=int(item["index"]),
        prompt=str(item["prompt"]),
        status=item.get("status", "pending"),
        key=item.get("key"),
        pptx_download_url=item.get("pptx_download_url"),
        thumbnail_urls=item.get("thumbnail_urls", []),
        error_type=item.get("error_type"),
        traceback=item.get("traceback"),
    )


def get_raw_prompt_pool() -> RawPromptPoolResponse:
    return RawPromptPoolResponse(
        system_prompt=RAW_PROMPT_SYSTEM_PROMPT,
        summary=_pool_summary(),
        items=[_pool_item_model(item) for item in RAW_PROMPT_POOL],
    )


def restore_raw_prompt_pool(payload: RawPromptPoolRestoreRequest) -> RawPromptPoolResponse:
    global RAW_PROMPT_SYSTEM_PROMPT

    restored_items = [item for item in payload.items if item.prompt.strip()]
    if not restored_items:
        raise ValueError("복원할 Raw Prompt 항목이 없습니다.")

    RAW_PROMPT_POOL.clear()
    for index, item in enumerate(restored_items, start=1):
        RAW_PROMPT_POOL.append(
            {
                "id": str(uuid.uuid4()),
                "index": index,
                "prompt": item.prompt.strip(),
                "status": item.status,
                "thumbnail_urls": [],
            }
        )

    if payload.system_prompt and payload.system_prompt.strip():
        RAW_PROMPT_SYSTEM_PROMPT = payload.system_prompt.strip()

    return get_raw_prompt_pool()


def _parse_raw_prompt_list(content: str, expected_count: int) -> List[str]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Raw Prompt 목록 JSON을 찾지 못했습니다.")
        payload = json.loads(match.group(0))

    prompts = payload.get("prompts") if isinstance(payload, dict) else None
    if not isinstance(prompts, list):
        raise ValueError("Raw Prompt JSON에는 prompts 배열이 필요합니다.")

    clean_prompts = [str(item).strip() for item in prompts if str(item).strip()]
    if len(clean_prompts) < expected_count:
        raise ValueError(f"Raw Prompt가 부족합니다. expected={expected_count}, actual={len(clean_prompts)}")
    return clean_prompts[:expected_count]


def generate_raw_prompt_pool(payload: RawPromptPoolGenerateRequest) -> RawPromptPoolResponse:
    global RAW_PROMPT_SYSTEM_PROMPT

    total = payload.prompt_count
    RAW_PROMPT_SYSTEM_PROMPT = generate_raw_prompt_system_prompt(
        endpoint=payload.lmstudio_endpoint,
        model=payload.lmstudio_model,
        topic_seed=payload.topic_seed,
    )

    prompts: List[str] = []
    remaining = total
    while remaining > 0:
        chunk = min(RAW_PROMPT_LIST_CHUNK_SIZE, remaining)
        raw_list = generate_raw_prompt_list(
            endpoint=payload.lmstudio_endpoint,
            model=payload.lmstudio_model,
            system_prompt=RAW_PROMPT_SYSTEM_PROMPT,
            prompt_count=chunk,
            topic_seed=payload.topic_seed,
        )
        batch = _parse_raw_prompt_list(raw_list, chunk)
        prompts.extend(batch)
        remaining -= chunk

    prompts = prompts[:total]

    RAW_PROMPT_POOL.clear()
    for index, prompt in enumerate(prompts, start=1):
        RAW_PROMPT_POOL.append(
            {
                "id": str(uuid.uuid4()),
                "index": index,
                "prompt": prompt,
                "status": "pending",
                "thumbnail_urls": [],
            }
        )
    saved_file = save_raw_prompt_pool_to_file(topic_seed=payload.topic_seed, prompt_count=total)
    response = get_raw_prompt_pool()
    return response.model_copy(update={"saved_file": saved_file})


def _thumbnail_urls_for_run(run_id: str, pptx_path: Path) -> List[str]:
    output_dir = TOOL_ARTIFACT_ROOT / run_id / "thumbnails"
    thumbnails = export_pptx_thumbnails(pptx_path, output_dir)
    return [f"/tools/dataset/previews/{run_id}/{path.name}" for path in thumbnails]


def _run_dataset_generation_loop(
    *,
    raw_prompt: str,
    endpoint: str,
    model: str,
    max_retries: int,
    system_prompt: Optional[str],
) -> Tuple[DatasetAutoGenerateResponse, Optional[str], Optional[Path]]:
    attempts: List[DatasetAutoAttempt] = []
    generated_markdown = ""
    parsed_user_prompt = None
    parsed_thinking = None
    parsed_python_code = None
    frozen_user_prompt: Optional[str] = None
    frozen_thinking: Optional[str] = None
    last_error_type: Optional[str] = None
    last_traceback: Optional[str] = None
    last_failure_kind: Optional[str] = None
    last_repair_target: Optional[str] = None
    prompt_key = build_key(raw_prompt)
    repair_session = load_repair_session(prompt_key)

    attempt = 0
    while True:
        attempt += 1
        if max_retries > 0 and attempt > max_retries + 1:
            break

        stage = "generate" if attempt == 1 else "repair"
        error_memory_addon = merge_repair_memory_addons(
            format_error_memory_for_prompt(),
            format_session_memory_for_prompt(repair_session),
        )
        attempt_repair_target = None
        attempt_failure_kind = None

        try:
            if stage == "generate":
                publish_live_answer_event(
                    {
                        "type": "repair_plan",
                        "stage": "generate_markdown_sample",
                        "attempt": attempt,
                        "repair_target": None,
                        "locked_fields": [],
                        "content": "1차 전체 생성 (User Prompt + Thinking + Assistant Python)",
                    }
                )
                generated_markdown = generate_markdown_sample(
                    endpoint=endpoint,
                    model=model,
                    raw_prompt=raw_prompt,
                    system_prompt=system_prompt,
                    error_memory_addon=error_memory_addon or None,
                )
            else:
                attempt_failure_kind, attempt_repair_target = classify_dataset_failure(
                    error_type=last_error_type,
                    traceback=last_traceback,
                    parsed={
                        "thinking": parsed_thinking or "",
                        "assistant_python": parsed_python_code or "",
                    },
                    frozen_thinking=frozen_thinking,
                )
                repair_ctx = build_repair_context(
                    failure_kind=attempt_failure_kind,
                    error_type=last_error_type or "UnknownError",
                    traceback=last_traceback or "Unknown error",
                    error_memory_addon=error_memory_addon,
                    raw_prompt=raw_prompt,
                    frozen_user_prompt=frozen_user_prompt or raw_prompt.strip(),
                    frozen_thinking=frozen_thinking or "",
                    failed_python_code=parsed_python_code or "",
                    previous_markdown=generated_markdown,
                    repair_target=attempt_repair_target,
                )
                locked_fields = ["user_prompt"]
                if attempt_repair_target == "assistant_python" and (frozen_thinking or "").strip():
                    locked_fields.append("thinking")
                if attempt_repair_target == "thinking" and (parsed_python_code or "").strip():
                    locked_fields.append("assistant_python")
                publish_live_answer_event(
                    {
                        "type": "repair_plan",
                        "stage": f"repair_{attempt_repair_target}_only",
                        "attempt": attempt,
                        "repair_target": attempt_repair_target,
                        "failure_kind": attempt_failure_kind,
                        "locked_fields": locked_fields,
                        "content": (
                            f"필드 단위 repair · attempt {attempt} · "
                            f"재생성={attempt_repair_target} · "
                            f"고정={', '.join(locked_fields)}"
                        ),
                    }
                )
                generated_markdown = execute_field_repair(
                    repair_ctx,
                    endpoint=endpoint,
                    model=model,
                )

            generated_markdown, parsed = _parse_markdown_with_raw_prompt(
                markdown=generated_markdown,
                raw_prompt=raw_prompt,
                endpoint=endpoint,
                model=model,
                error_memory_addon=error_memory_addon or None,
            )
            parsed_user_prompt = parsed["user_prompt"]
            parsed_thinking = parsed["thinking"]
            parsed_python_code = parsed["assistant_python"]

            if frozen_user_prompt is None:
                frozen_user_prompt = raw_prompt.strip()
            if frozen_thinking is None and (parsed_thinking or "").strip():
                frozen_thinking = parsed_thinking

            parse_gap = missing_repair_target(parsed)
            if parse_gap:
                last_error_type = "ParseError"
                last_traceback = f"Missing or empty section: {parse_gap}"
                last_failure_kind, last_repair_target = classify_dataset_failure(
                    error_type=last_error_type,
                    traceback=last_traceback,
                    parsed=parsed,
                    frozen_thinking=frozen_thinking,
                )
                record_error(error_type=last_error_type, traceback_text=last_traceback)
                record_repair_session_error(
                    repair_session,
                    raw_prompt=raw_prompt,
                    attempt=attempt,
                    error_type=last_error_type,
                    traceback_text=last_traceback,
                    repair_target=last_repair_target,
                    failure_kind=last_failure_kind,
                    failed_python_code=parsed_python_code or "",
                )
                attempts.append(
                    DatasetAutoAttempt(
                        attempt=attempt,
                        stage=stage,
                        status="error",
                        error_type=last_error_type,
                        traceback=last_traceback,
                        repair_target=last_repair_target,
                        failure_kind=last_failure_kind,
                    )
                )
                continue

            publish_live_answer_event(
                {
                    "type": "repair_plan",
                    "stage": "python_validation",
                    "attempt": attempt,
                    "repair_target": None,
                    "locked_fields": [],
                    "content": f"attempt {attempt} · Python 실행 검증 중…",
                }
            )
            validation, run_id, pptx_path = _run_python_and_save_ppt(parsed_python_code)
            if validation.status == "ok":
                clear_repair_session(prompt_key)
                key = upsert_pair(
                    user_prompt=raw_prompt.strip(),
                    asset_code="",
                    python_code=generated_markdown,
                    asset_system_prompt=ASSET_SYSTEM_PROMPT,
                    python_system_prompt=PYTHON_SYSTEM_PROMPT,
                )
                attempts.append(
                    DatasetAutoAttempt(
                        attempt=attempt,
                        stage=stage,
                        status="ok",
                        logs=validation.logs,
                        repair_target=attempt_repair_target if stage == "repair" else None,
                        failure_kind=attempt_failure_kind if stage == "repair" else None,
                    )
                )
                return (
                    DatasetAutoGenerateResponse(
                        status="ok",
                        key=key,
                        generated_markdown=generated_markdown,
                        parsed_user_prompt=parsed_user_prompt,
                        parsed_thinking=parsed_thinking,
                        parsed_python_code=parsed_python_code,
                        attempts=attempts,
                        validation=validation,
                        dataset_row=build_data_messages_row(
                            system_prompt=(system_prompt or PYTHON_SYSTEM_PROMPT).strip(),
                            user_prompt=raw_prompt.strip(),
                            assistant_markdown=generated_markdown,
                        ),
                    ),
                    run_id,
                    pptx_path,
                )

            last_error_type = validation.error_type or "ExecutionError"
            last_traceback = validation.traceback or "Python execution failed"
            last_failure_kind, last_repair_target = classify_dataset_failure(
                error_type=last_error_type,
                traceback=last_traceback,
                parsed=parsed,
                frozen_thinking=frozen_thinking,
            )
            record_error(error_type=last_error_type, traceback_text=last_traceback)
            record_repair_session_error(
                repair_session,
                raw_prompt=raw_prompt,
                attempt=attempt,
                error_type=last_error_type,
                traceback_text=last_traceback,
                repair_target=last_repair_target,
                failure_kind=last_failure_kind,
                failed_python_code=parsed_python_code or "",
            )
            attempts.append(
                DatasetAutoAttempt(
                    attempt=attempt,
                    stage=stage,
                    status="error",
                    error_type=last_error_type,
                    traceback=last_traceback,
                    logs=validation.logs,
                    repair_target=last_repair_target,
                    failure_kind=last_failure_kind,
                )
            )
        except (LMStudioError, ValueError) as exc:
            last_error_type = "GenerationError"
            last_traceback = str(exc)
            last_failure_kind, last_repair_target = classify_dataset_failure(
                error_type=last_error_type,
                traceback=last_traceback,
                parsed={
                    "thinking": parsed_thinking or "",
                    "assistant_python": parsed_python_code or "",
                }
                if parsed_thinking is not None or parsed_python_code
                else None,
                frozen_thinking=frozen_thinking,
            )
            record_error(error_type=last_error_type, traceback_text=last_traceback)
            record_repair_session_error(
                repair_session,
                raw_prompt=raw_prompt,
                attempt=attempt,
                error_type=last_error_type,
                traceback_text=last_traceback,
                repair_target=last_repair_target,
                failure_kind=last_failure_kind,
                failed_python_code=parsed_python_code or "",
            )
            attempts.append(
                DatasetAutoAttempt(
                    attempt=attempt,
                    stage=stage,
                    status="error",
                    error_type=last_error_type,
                    traceback=last_traceback,
                    repair_target=last_repair_target,
                    failure_kind=last_failure_kind,
                )
            )

    return (
        DatasetAutoGenerateResponse(
            status="error",
            generated_markdown=generated_markdown or None,
            parsed_user_prompt=parsed_user_prompt,
            parsed_thinking=parsed_thinking,
            parsed_python_code=parsed_python_code,
            attempts=attempts,
            error_type=last_error_type or "UnknownError",
            traceback=last_traceback or "자동화 처리 실패",
        ),
        None,
        None,
    )


def _generate_validate_save_for_prompt(
    *,
    raw_prompt: str,
    endpoint: str,
    model: str,
    max_retries: int,
    system_prompt: Optional[str],
) -> Tuple[DatasetAutoGenerateResponse, Optional[str], Optional[Path]]:
    return _run_dataset_generation_loop(
        raw_prompt=raw_prompt,
        endpoint=endpoint,
        model=model,
        max_retries=max_retries,
        system_prompt=system_prompt,
    )


def consume_raw_prompt_pool(payload: RawPromptPoolConsumeRequest) -> RawPromptPoolConsumeResponse:
    pending_items = [item for item in RAW_PROMPT_POOL if item.get("status") == "pending"]
    selected = pending_items[: payload.count]
    results: List[RawPromptPoolConsumeItemResult] = []

    for item in selected:
        item["status"] = "processing"
        custom_sp = (payload.system_prompt or "").strip()
        system_for_run = custom_sp if custom_sp else RAW_PROMPT_SYSTEM_PROMPT
        response, run_id, pptx_path = _generate_validate_save_for_prompt(
            raw_prompt=str(item["prompt"]),
            endpoint=payload.lmstudio_endpoint,
            model=payload.lmstudio_model,
            max_retries=payload.max_retries,
            system_prompt=system_for_run,
        )

        thumbnail_urls: List[str] = []
        if response.status == "ok" and run_id and pptx_path:
            try:
                thumbnail_urls = _thumbnail_urls_for_run(run_id, pptx_path)
            except Exception as exc:
                thumbnail_urls = []
                item["preview_error"] = str(exc)

        item["key"] = response.key
        item["pptx_download_url"] = response.validation.pptx_download_url if response.validation else None
        item["thumbnail_urls"] = thumbnail_urls
        item["error_type"] = response.error_type
        item["traceback"] = response.traceback
        item["status"] = "done" if response.status == "ok" else "failed"

        results.append(
            RawPromptPoolConsumeItemResult(
                prompt_id=str(item["id"]),
                status=response.status,
                key=response.key,
                prompt=str(item["prompt"]),
                pptx_download_url=item.get("pptx_download_url"),
                thumbnail_urls=thumbnail_urls,
                attempts=response.attempts,
                error_type=response.error_type,
                traceback=response.traceback or item.get("preview_error"),
            )
        )

    success = sum(1 for item in results if item.status == "ok")
    failed = sum(1 for item in results if item.status == "error")
    return RawPromptPoolConsumeResponse(
        processed=len(results),
        success=success,
        failed=failed,
        summary=_pool_summary(),
        results=results,
    )


def auto_generate_dataset_entry(payload: DatasetAutoGenerateRequest) -> DatasetAutoGenerateResponse:
    response, _, _ = _run_dataset_generation_loop(
        raw_prompt=payload.raw_prompt,
        endpoint=payload.lmstudio_endpoint,
        model=payload.lmstudio_model,
        max_retries=payload.max_retries,
        system_prompt=payload.system_prompt,
    )
    return response
