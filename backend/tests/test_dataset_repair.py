from unittest.mock import patch

import pytest

from app.services.dataset_repair import (
    assemble_dataset_markdown,
    build_repair_context,
    classify_dataset_failure,
    execute_field_repair,
    missing_repair_target,
)


def test_classify_execution_error_targets_assistant_python():
    kind, target = classify_dataset_failure(
        error_type="ExecutionError",
        traceback="ValueError: bad chart enum",
        parsed={"thinking": "Plan slide 1", "assistant_python": "print(1)"},
        frozen_thinking="Plan slide 1",
    )
    assert kind == "execution"
    assert target == "assistant_python"


def test_classify_execution_without_thinking_targets_thinking():
    kind, target = classify_dataset_failure(
        error_type="ExecutionError",
        traceback="ValueError: bad chart enum",
        parsed={"thinking": "", "assistant_python": "print(1)"},
        frozen_thinking="",
    )
    assert kind == "parse_thinking"
    assert target == "thinking"


def test_classify_thinking_parse_message():
    kind, target = classify_dataset_failure(
        error_type="ParseError",
        traceback="섹션 파싱 실패: Thinking",
        parsed={"thinking": "", "assistant_python": ""},
    )
    assert kind == "parse_thinking"
    assert target == "thinking"


def test_classify_generation_error_with_frozen_thinking_targets_python():
    kind, target = classify_dataset_failure(
        error_type="GenerationError",
        traceback="재시도 응답에서 Python 코드 블록을 찾지 못했습니다.",
        parsed={"thinking": "plan", "assistant_python": "print(1)"},
        frozen_thinking="plan",
    )
    assert kind == "parse_assistant"
    assert target == "assistant_python"

    kind, target = classify_dataset_failure(
        error_type="ParseError",
        traceback="섹션 파싱 실패: Assistant",
        parsed={"thinking": "ok", "assistant_python": ""},
    )
    assert kind == "parse_assistant"
    assert target == "assistant_python"


def test_missing_repair_target_prefers_thinking():
    assert missing_repair_target({"thinking": "", "assistant_python": "x = 1"}) == "thinking"
    assert missing_repair_target({"thinking": "plan", "assistant_python": ""}) == "assistant_python"
    assert missing_repair_target({"thinking": "plan", "assistant_python": "x = 1"}) is None


def test_assemble_dataset_markdown_preserves_sections():
    md = assemble_dataset_markdown("user text", "thinking text", "print('hi')")
    assert "# User Prompt" in md
    assert "# Thinking" in md
    assert "# Assistant" in md
    assert "user text" in md
    assert "thinking text" in md
    assert "print('hi')" in md


@patch("app.services.dataset_repair.repair_assistant_python_only")
def test_execute_field_repair_python_keeps_frozen_fields(mock_repair):
    mock_repair.return_value = "print('fixed')"
    ctx = build_repair_context(
        failure_kind="execution",
        error_type="ExecutionError",
        traceback="ValueError: x",
        error_memory_addon="memory block",
        raw_prompt="raw request",
        frozen_user_prompt="locked user",
        frozen_thinking="locked thinking",
        failed_python_code="print('bad')",
        previous_markdown="# old",
        repair_target="assistant_python",
    )
    result = execute_field_repair(ctx, endpoint="http://localhost:1234/v1/chat/completions", model="m")
    assert "locked user" in result
    assert "locked thinking" in result
    assert "print('fixed')" in result
    mock_repair.assert_called_once()
    call_kwargs = mock_repair.call_args.kwargs
    assert call_kwargs["error_type"] == "ExecutionError"
    assert call_kwargs["failure_kind"] == "execution"
    assert call_kwargs["repair_target"] == "assistant_python"
    assert call_kwargs["fixed_user_prompt"] == "locked user"
    assert call_kwargs["fixed_thinking"] == "locked thinking"


@patch("app.services.dataset_repair.repair_thinking_only")
def test_execute_field_repair_routes_empty_thinking_before_python(mock_thinking_repair):
    mock_thinking_repair.return_value = "new thinking plan"
    ctx = build_repair_context(
        failure_kind="execution",
        error_type="ExecutionError",
        traceback="ValueError: x",
        error_memory_addon="",
        raw_prompt="raw request",
        frozen_user_prompt="locked user",
        frozen_thinking="",
        failed_python_code="print('bad')",
        previous_markdown="# old",
        repair_target="assistant_python",
    )
    result = execute_field_repair(ctx, endpoint="http://localhost:1234/v1/chat/completions", model="m")
    mock_thinking_repair.assert_called_once()
    assert "new thinking plan" in result
    assert "locked user" in result
    assert "print('bad')" in result
