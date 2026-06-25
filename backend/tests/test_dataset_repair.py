from unittest.mock import patch

import pytest

from app.services.lm_studio_service import LMStudioError, _extract_code_replacements, _post_chat_completion
from app.services.dataset_service import build_data_messages_row, resolve_dataset_system_prompt
from app.services.dataset_repair import (
    apply_code_replacements,
    assemble_dataset_markdown,
    build_repair_context,
    classify_dataset_failure,
    execute_field_repair,
    missing_repair_target,
)


def test_extract_code_replacements_accepts_json_and_json_fence():
    expected = [{"old_code": "value = 1", "new_code": "value = 2"}]
    assert _extract_code_replacements(
        '{"replacements":[{"old_code":"value = 1","new_code":"value = 2"}]}'
    ) == expected
    assert _extract_code_replacements(
        '```json\n{"replacements":[{"old_code":"value = 1","new_code":"value = 2"}]}\n```'
    ) == expected


def test_extract_code_replacements_rejects_empty_or_unchanged_patch():
    with pytest.raises(LMStudioError, match="replacements 배열"):
        _extract_code_replacements('{"replacements":[]}')

    with pytest.raises(LMStudioError, match="실제 코드 변경이 없습니다"):
        _extract_code_replacements(
            '{"replacements":[{"old_code":"value = 1","new_code":"value = 1"}]}'
        )


def test_extract_code_replacements_rejects_markdown_fences():
    with pytest.raises(LMStudioError, match="Markdown 코드 fence"):
        _extract_code_replacements(
            '{"replacements":[{"old_code":"```python\\nvalue = 1\\n```","new_code":"value = 2"}]}'
        )


@patch("app.services.lm_studio_service._iter_openai_sse_data")
def test_empty_lm_content_reports_reasoning_and_finish_reason(mock_stream):
    mock_stream.return_value = iter(
        [
            '{"choices":[{"delta":{"reasoning_content":"thinking"},"finish_reason":"length"}]}',
            "[DONE]",
        ]
    )
    with pytest.raises(LMStudioError, match="finish_reason=length, reasoning_chars=8"):
        _post_chat_completion("http://localhost:1234/v1/chat/completions", {"model": "m"})


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


def test_build_data_messages_row_stores_only_assistant_code():
    code = "from pptx import Presentation\nPresentation().save('output.pptx')"
    row = build_data_messages_row("system", "user request", code)
    messages = row["data"]["messages"]
    assert messages[2] == {"role": "assistant", "content": code}
    assert "# Thinking" not in messages[2]["content"]


def test_dataset_system_prompt_does_not_fall_back_to_raw_prompt_generator():
    assert resolve_dataset_system_prompt(None) is None
    assert resolve_dataset_system_prompt("   ") is None
    assert resolve_dataset_system_prompt(" custom dataset prompt ") == "custom dataset prompt"


def test_apply_code_replacements_changes_only_exact_fragment():
    source = "def main():\n    value = 1\n    print(value)\n"
    patched = apply_code_replacements(
        source,
        [{"old_code": "    value = 1", "new_code": "    value = 2"}],
    )
    assert patched == "def main():\n    value = 2\n    print(value)\n"


def test_apply_code_replacements_rejects_missing_or_ambiguous_fragment():
    with pytest.raises(ValueError, match="찾지 못했습니다"):
        apply_code_replacements("value = 1\n", [{"old_code": "value = 2", "new_code": "value = 3"}])

    with pytest.raises(ValueError, match="2곳"):
        apply_code_replacements(
            "value = 1\nvalue = 1\n",
            [{"old_code": "value = 1", "new_code": "value = 2"}],
        )


def test_apply_code_replacements_rejects_invalid_python():
    with pytest.raises(ValueError, match="Python 문법 오류"):
        apply_code_replacements(
            "value = 1\n",
            [{"old_code": "value = 1", "new_code": "if:"}],
        )


def test_apply_code_replacements_rejects_complete_script_response():
    source = "def helper():\n    return 1\n\ndef main():\n    helper()\n\nif __name__ == \"__main__\":\n    main()\n"
    complete_script = (
        "from pptx import Presentation\n\n"
        "def main():\n    Presentation().save('output.pptx')\n\n"
        "if __name__ == \"__main__\":\n    main()"
    )
    with pytest.raises(ValueError, match="전체 스크립트 재생성"):
        apply_code_replacements(
            source,
            [{"old_code": "    return 1", "new_code": complete_script}],
        )


@patch("app.services.dataset_repair.repair_assistant_python_only")
def test_execute_field_repair_python_keeps_frozen_fields(mock_repair):
    mock_repair.return_value = [{"old_code": "print('bad')", "new_code": "print('fixed')"}]
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
