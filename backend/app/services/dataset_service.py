from __future__ import annotations

import hashlib
import json
import re
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
    RawPromptPoolRestoreRequest,
    RawPromptPoolItem,
    RawPromptPoolResponse,
    RawPromptPoolSummary,
)
from app.models.schemas import PPTCodeBundle, PythonValidationResponse
from app.services.lm_studio_service import (
    LMStudioError,
    generate_markdown_sample,
    generate_raw_prompt_list,
    generate_raw_prompt_system_prompt,
    repair_assistant_python_only,
    repair_markdown_sample,
    repair_thinking_only,
)
from app.services.ppt_preview_service import export_pptx_thumbnails
from app.services.pptx_error_memory import format_error_memory_for_prompt, record_error
from app.services.runner_service import run_ppt_code

DATASET_DIR = Path("data/datasets")
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
THINKING_SECTION_PARSE_ERROR = "섹션 파싱 실패: Thinking"


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
    return {
        "user_prompt": user_prompt,
        "thinking": _extract_section_block(markdown, "Thinking", "text"),
        "assistant_python": _extract_section_block(markdown, "Assistant", "python"),
    }


def _assemble_dataset_markdown(fixed_user_prompt: str, fixed_thinking: str, assistant_python: str) -> str:
    return (
        "# User Prompt\n```text\n"
        + fixed_user_prompt.strip()
        + "\n```\n\n# Thinking\n```text\n"
        + fixed_thinking.strip()
        + "\n```\n\n# Assistant\n```python\n"
        + assistant_python.strip()
        + "\n```\n"
    )


def _is_thinking_section_parse_error(exc: ValueError) -> bool:
    return str(exc) == THINKING_SECTION_PARSE_ERROR


def _parse_markdown_with_raw_prompt(
    *,
    markdown: str,
    raw_prompt: str,
    endpoint: str,
    model: str,
    error_memory_addon: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    try:
        parsed = parse_markdown_dataset(markdown, raw_prompt=raw_prompt)
    except ValueError as exc:
        if not _is_thinking_section_parse_error(exc):
            raise

        assistant_python = _try_extract_section_block(markdown, "Assistant", "python")
        if not assistant_python:
            raise

        fixed_user_prompt = raw_prompt.strip()
        repaired_thinking = repair_thinking_only(
            endpoint=endpoint,
            model=model,
            raw_prompt=raw_prompt,
            fixed_user_prompt=fixed_user_prompt,
            previous_markdown=markdown,
            error_memory_addon=error_memory_addon,
        )
        repaired_markdown = _assemble_dataset_markdown(
            fixed_user_prompt,
            repaired_thinking,
            assistant_python,
        )
        return repaired_markdown, parse_markdown_dataset(repaired_markdown, raw_prompt=raw_prompt)

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
    return get_raw_prompt_pool()


def _thumbnail_urls_for_run(run_id: str, pptx_path: Path) -> List[str]:
    output_dir = TOOL_ARTIFACT_ROOT / run_id / "thumbnails"
    thumbnails = export_pptx_thumbnails(pptx_path, output_dir)
    return [f"/tools/dataset/previews/{run_id}/{path.name}" for path in thumbnails]


def _generate_validate_save_for_prompt(
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
    last_error_type = None
    last_traceback = None

    for attempt in range(1, max_retries + 2):
        stage = "generate" if attempt == 1 else "repair"
        error_memory_addon = format_error_memory_for_prompt()
        try:
            if stage == "generate":
                generated_markdown = generate_markdown_sample(
                    endpoint=endpoint,
                    model=model,
                    raw_prompt=raw_prompt,
                    system_prompt=system_prompt,
                    error_memory_addon=error_memory_addon or None,
                )
            elif (
                frozen_user_prompt is not None
                and frozen_thinking is not None
                and (parsed_python_code or "").strip()
            ):
                new_python = repair_assistant_python_only(
                    endpoint=endpoint,
                    model=model,
                    raw_prompt=raw_prompt,
                    fixed_user_prompt=frozen_user_prompt,
                    fixed_thinking=frozen_thinking,
                    failed_python_code=parsed_python_code or "",
                    traceback_text=last_traceback or "Unknown execution error",
                    error_memory_addon=error_memory_addon or None,
                )
                generated_markdown = _assemble_dataset_markdown(
                    frozen_user_prompt, frozen_thinking, new_python
                )
            else:
                generated_markdown = repair_markdown_sample(
                    endpoint=endpoint,
                    model=model,
                    raw_prompt=raw_prompt,
                    previous_markdown=generated_markdown,
                    failed_python_code=parsed_python_code or "",
                    traceback_text=last_traceback or "Unknown execution error",
                    error_memory_addon=error_memory_addon or None,
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
                frozen_thinking = parsed_thinking

            validation, run_id, pptx_path = _run_python_and_save_ppt(parsed_python_code)
            if validation.status == "ok":
                key = upsert_pair(
                    user_prompt=raw_prompt.strip(),
                    asset_code="",
                    python_code=generated_markdown,
                    asset_system_prompt=ASSET_SYSTEM_PROMPT,
                    python_system_prompt=PYTHON_SYSTEM_PROMPT,
                )
                attempts.append(DatasetAutoAttempt(attempt=attempt, stage=stage, status="ok", logs=validation.logs))
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
            record_error(error_type=last_error_type, traceback_text=last_traceback)
            attempts.append(
                DatasetAutoAttempt(
                    attempt=attempt,
                    stage=stage,
                    status="error",
                    error_type=last_error_type,
                    traceback=last_traceback,
                    logs=validation.logs,
                )
            )
        except (LMStudioError, ValueError) as exc:
            last_error_type = "GenerationError"
            last_traceback = str(exc)
            record_error(error_type=last_error_type, traceback_text=last_traceback)
            attempts.append(
                DatasetAutoAttempt(
                    attempt=attempt,
                    stage=stage,
                    status="error",
                    error_type=last_error_type,
                    traceback=last_traceback,
                    logs=[],
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
    attempts: List[DatasetAutoAttempt] = []
    generated_markdown = ""
    parsed_user_prompt = None
    parsed_thinking = None
    parsed_python_code = None
    frozen_user_prompt: Optional[str] = None
    frozen_thinking: Optional[str] = None
    last_error_type = None
    last_traceback = None

    for attempt in range(1, payload.max_retries + 2):
        stage = "generate" if attempt == 1 else "repair"
        error_memory_addon = format_error_memory_for_prompt()
        try:
            if stage == "generate":
                generated_markdown = generate_markdown_sample(
                    endpoint=payload.lmstudio_endpoint,
                    model=payload.lmstudio_model,
                    raw_prompt=payload.raw_prompt,
                    system_prompt=payload.system_prompt,
                    error_memory_addon=error_memory_addon or None,
                )
            elif (
                frozen_user_prompt is not None
                and frozen_thinking is not None
                and (parsed_python_code or "").strip()
            ):
                new_python = repair_assistant_python_only(
                    endpoint=payload.lmstudio_endpoint,
                    model=payload.lmstudio_model,
                    raw_prompt=payload.raw_prompt,
                    fixed_user_prompt=frozen_user_prompt,
                    fixed_thinking=frozen_thinking,
                    failed_python_code=parsed_python_code or "",
                    traceback_text=last_traceback or "Unknown execution error",
                    error_memory_addon=error_memory_addon or None,
                )
                generated_markdown = _assemble_dataset_markdown(
                    frozen_user_prompt, frozen_thinking, new_python
                )
            else:
                generated_markdown = repair_markdown_sample(
                    endpoint=payload.lmstudio_endpoint,
                    model=payload.lmstudio_model,
                    raw_prompt=payload.raw_prompt,
                    previous_markdown=generated_markdown,
                    failed_python_code=parsed_python_code or "",
                    traceback_text=last_traceback or "Unknown execution error",
                    error_memory_addon=error_memory_addon or None,
                )

            generated_markdown, parsed = _parse_markdown_with_raw_prompt(
                markdown=generated_markdown,
                raw_prompt=payload.raw_prompt,
                endpoint=payload.lmstudio_endpoint,
                model=payload.lmstudio_model,
                error_memory_addon=error_memory_addon or None,
            )
            parsed_user_prompt = parsed["user_prompt"]
            parsed_thinking = parsed["thinking"]
            parsed_python_code = parsed["assistant_python"]
            if frozen_user_prompt is None:
                frozen_user_prompt = payload.raw_prompt.strip()
                frozen_thinking = parsed_thinking

            validation = validate_python_and_save_ppt(parsed_python_code)
            if validation.status == "ok":
                key = upsert_pair(
                    user_prompt=payload.raw_prompt.strip(),
                    asset_code="",
                    python_code=generated_markdown,
                    asset_system_prompt=ASSET_SYSTEM_PROMPT,
                    python_system_prompt=PYTHON_SYSTEM_PROMPT,
                )
                dataset_row = build_data_messages_row(
                    system_prompt=(payload.system_prompt or PYTHON_SYSTEM_PROMPT).strip(),
                    user_prompt=payload.raw_prompt.strip(),
                    assistant_markdown=generated_markdown,
                )
                attempts.append(
                    DatasetAutoAttempt(
                        attempt=attempt,
                        stage=stage,
                        status="ok",
                        logs=validation.logs,
                    )
                )
                return DatasetAutoGenerateResponse(
                    status="ok",
                    key=key,
                    generated_markdown=generated_markdown,
                    parsed_user_prompt=parsed_user_prompt,
                    parsed_thinking=parsed_thinking,
                    parsed_python_code=parsed_python_code,
                    attempts=attempts,
                    validation=validation,
                    dataset_row=dataset_row,
                )

            last_error_type = validation.error_type or "ExecutionError"
            last_traceback = validation.traceback or "Python execution failed"
            record_error(error_type=last_error_type, traceback_text=last_traceback)
            attempts.append(
                DatasetAutoAttempt(
                    attempt=attempt,
                    stage=stage,
                    status="error",
                    error_type=last_error_type,
                    traceback=last_traceback,
                    logs=validation.logs,
                )
            )
        except (LMStudioError, ValueError) as exc:
            last_error_type = "GenerationError"
            last_traceback = str(exc)
            record_error(error_type=last_error_type, traceback_text=last_traceback)
            attempts.append(
                DatasetAutoAttempt(
                    attempt=attempt,
                    stage=stage,
                    status="error",
                    error_type=last_error_type,
                    traceback=last_traceback,
                    logs=[],
                )
            )

    return DatasetAutoGenerateResponse(
        status="error",
        generated_markdown=generated_markdown or None,
        parsed_user_prompt=parsed_user_prompt,
        parsed_thinking=parsed_thinking,
        parsed_python_code=parsed_python_code,
        attempts=attempts,
        error_type=last_error_type or "UnknownError",
        traceback=last_traceback or "자동화 처리 실패",
    )
