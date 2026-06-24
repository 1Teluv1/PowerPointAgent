from pathlib import Path

import pytest

from app.services import dataset_repair_session as session_mod


def test_record_and_format_session_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(session_mod, "SESSION_DIR", tmp_path)

    repair_session = session_mod.load_repair_session("abc123")
    session_mod.record_repair_session_error(
        repair_session,
        raw_prompt="Generate an 8-slide deck",
        attempt=1,
        error_type="ExecutionError",
        traceback_text="AttributeError: 'tuple' object has no attribute 'xml_bytes'",
        repair_target="assistant_python",
        failure_kind="execution",
        failed_python_code="slide.shapes.add_chart(...)",
    )
    session_mod.record_repair_session_error(
        repair_session,
        raw_prompt="Generate an 8-slide deck",
        attempt=2,
        error_type="ExecutionError",
        traceback_text="ValueError: chart data invalid",
        repair_target="assistant_python",
        failure_kind="execution",
        failed_python_code="slide.shapes.add_chart(...)",
    )

    text = session_mod.format_session_memory_for_prompt(repair_session)
    assert "Repair session history" in text
    assert "Attempt 1" in text
    assert "Attempt 2" in text
    assert "xml_bytes" in text

    loaded = session_mod.load_repair_session("abc123")
    assert len(loaded.turns) == 2


def test_clear_session_removes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(session_mod, "SESSION_DIR", tmp_path)

    repair_session = session_mod.load_repair_session("key1")
    session_mod.record_repair_session_error(
        repair_session,
        raw_prompt="test",
        attempt=1,
        error_type="ParseError",
        traceback_text="missing thinking",
    )
    assert session_mod._session_path("key1").exists()

    session_mod.clear_repair_session("key1")
    assert not session_mod._session_path("key1").exists()


def test_merge_repair_memory_addons():
    merged = session_mod.merge_repair_memory_addons("global memory", "session memory")
    assert "global memory" in merged
    assert "session memory" in merged
    assert merged.index("global memory") < merged.index("session memory")
