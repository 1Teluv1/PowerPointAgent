from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple

from app.services.lm_studio_service import (
    repair_assistant_python_only,
    repair_thinking_only,
)

DatasetFailureKind = Literal["execution", "parse_thinking", "parse_assistant", "generation"]
DatasetRepairTarget = Literal["thinking", "assistant_python"]


def _thinking_excerpt_from_markdown(markdown: str) -> str:
    import re

    match = re.search(
        r"(?:^|\n)\#\s*Thinking\s*\n\s*```(?:text)?\s*\n(.*?)\n```",
        markdown or "",
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""


@dataclass
class DatasetRepairContext:
    failure_kind: DatasetFailureKind
    error_type: str
    traceback: str
    error_memory_addon: str
    raw_prompt: str
    frozen_user_prompt: str
    frozen_thinking: str
    failed_python_code: str
    previous_markdown: str
    repair_target: DatasetRepairTarget


def assemble_dataset_markdown(fixed_user_prompt: str, fixed_thinking: str, assistant_python: str) -> str:
    return (
        "# User Prompt\n```text\n"
        + fixed_user_prompt.strip()
        + "\n```\n\n# Thinking\n```text\n"
        + fixed_thinking.strip()
        + "\n```\n\n# Assistant\n```python\n"
        + assistant_python.strip()
        + "\n```\n"
    )


def missing_repair_target(parsed: Optional[Dict[str, str]]) -> Optional[DatasetRepairTarget]:
    if not parsed:
        return None
    thinking = (parsed.get("thinking") or "").strip()
    assistant = (parsed.get("assistant_python") or "").strip()
    if not thinking:
        return "thinking"
    if not assistant:
        return "assistant_python"
    return None


def classify_dataset_failure(
    *,
    error_type: Optional[str],
    traceback: Optional[str],
    parsed: Optional[Dict[str, str]] = None,
    frozen_thinking: Optional[str] = None,
) -> Tuple[DatasetFailureKind, DatasetRepairTarget]:
    et = (error_type or "").strip()
    tb = (traceback or "").strip()

    if et in ("ExecutionError", "MissingOutput"):
        if not (frozen_thinking or "").strip():
            return "parse_thinking", "thinking"
        return "execution", "assistant_python"

    if "Thinking" in tb or "섹션 파싱 실패: Thinking" in tb:
        return "parse_thinking", "thinking"
    if "Assistant" in tb or "섹션 파싱 실패: Assistant" in tb:
        return "parse_assistant", "assistant_python"

    gap = missing_repair_target(parsed)
    if gap == "thinking":
        return "parse_thinking", "thinking"
    if gap == "assistant_python":
        return "parse_assistant", "assistant_python"

    if et == "ParseError":
        return "parse_thinking", "thinking"

    if et == "GenerationError":
        if gap == "assistant_python":
            return "parse_assistant", "assistant_python"
        if gap == "thinking":
            return "parse_thinking", "thinking"
        if (frozen_thinking or "").strip():
            return "parse_assistant", "assistant_python"

    return "generation", "thinking"


def build_repair_context(
    *,
    failure_kind: DatasetFailureKind,
    error_type: str,
    traceback: str,
    error_memory_addon: str,
    raw_prompt: str,
    frozen_user_prompt: str,
    frozen_thinking: str,
    failed_python_code: str,
    previous_markdown: str,
    repair_target: DatasetRepairTarget,
) -> DatasetRepairContext:
    return DatasetRepairContext(
        failure_kind=failure_kind,
        error_type=error_type,
        traceback=traceback,
        error_memory_addon=error_memory_addon,
        raw_prompt=raw_prompt,
        frozen_user_prompt=frozen_user_prompt,
        frozen_thinking=frozen_thinking,
        failed_python_code=failed_python_code,
        previous_markdown=previous_markdown,
        repair_target=repair_target,
    )


def execute_field_repair(
    ctx: DatasetRepairContext,
    *,
    endpoint: str,
    model: str,
) -> str:
    user_prompt = ctx.frozen_user_prompt.strip() or ctx.raw_prompt.strip()

    if ctx.repair_target == "assistant_python" and not ctx.frozen_thinking.strip():
        ctx = DatasetRepairContext(
            failure_kind="parse_thinking",
            error_type=ctx.error_type,
            traceback=ctx.traceback or "Thinking section required before Python repair",
            error_memory_addon=ctx.error_memory_addon,
            raw_prompt=ctx.raw_prompt,
            frozen_user_prompt=user_prompt,
            frozen_thinking=ctx.frozen_thinking,
            failed_python_code=ctx.failed_python_code,
            previous_markdown=ctx.previous_markdown,
            repair_target="thinking",
        )

    if ctx.repair_target == "thinking":
        previous_thinking = ctx.frozen_thinking.strip() or _thinking_excerpt_from_markdown(ctx.previous_markdown)
        new_thinking = repair_thinking_only(
            endpoint=endpoint,
            model=model,
            raw_prompt=ctx.raw_prompt,
            fixed_user_prompt=user_prompt,
            previous_thinking_excerpt=previous_thinking,
            error_type=ctx.error_type,
            failure_kind=ctx.failure_kind,
            repair_target=ctx.repair_target,
            traceback_text=ctx.traceback,
            error_memory_addon=ctx.error_memory_addon or None,
        )
        return assemble_dataset_markdown(
            user_prompt,
            new_thinking,
            ctx.failed_python_code,
        )

    new_python = repair_assistant_python_only(
        endpoint=endpoint,
        model=model,
        raw_prompt=ctx.raw_prompt,
        fixed_user_prompt=user_prompt,
        fixed_thinking=ctx.frozen_thinking,
        failed_python_code=ctx.failed_python_code,
        traceback_text=ctx.traceback,
        error_type=ctx.error_type,
        failure_kind=ctx.failure_kind,
        repair_target=ctx.repair_target,
        error_memory_addon=ctx.error_memory_addon or None,
    )
    return assemble_dataset_markdown(user_prompt, ctx.frozen_thinking, new_python)
