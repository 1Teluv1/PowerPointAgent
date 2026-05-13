from pathlib import Path

import pytest

from app.services import pptx_error_memory as mem


def test_normalize_collapses_paths_for_same_fingerprint():
    a = mem.normalize_traceback_for_fingerprint(
        r'File "D:\proj\run.py", line 10' + "\nValueError: bad index"
    )
    b = mem.normalize_traceback_for_fingerprint(
        'File "/home/user/run.py", line 10\nValueError: bad index'
    )
    assert a == b
    assert "<PATH>" in a


def test_record_merges_same_error_increments_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = tmp_path / "pptx_error_memory.json"
    monkeypatch.setattr(mem, "ERROR_MEMORY_FILE", store)

    mem.record_error(
        error_type="ExecutionError",
        traceback_text=r'File "C:\a\x.py", line 1' + "\nValueError: x must be positive",
    )
    mem.record_error(
        error_type="ExecutionError",
        traceback_text=r'File "D:\b\y.py", line 1' + "\nValueError: x must be positive",
    )

    data = mem.load_store()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["occurrence_count"] == 2


def test_format_prompt_respects_total_max_chars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = tmp_path / "pptx_error_memory.json"
    monkeypatch.setattr(mem, "ERROR_MEMORY_FILE", store)

    for i in range(3):
        mem.record_error(
            error_type="ExecutionError",
            traceback_text=f"Error {i}: " + ("x" * 800),
        )

    text = mem.format_error_memory_for_prompt(total_max_chars=200)
    assert len(text) <= 200
    assert text.endswith("...")


def test_different_error_types_remain_separate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = tmp_path / "pptx_error_memory.json"
    monkeypatch.setattr(mem, "ERROR_MEMORY_FILE", store)

    mem.record_error(error_type="ExecutionError", traceback_text="Same message line")
    mem.record_error(error_type="MissingOutput", traceback_text="Same message line")

    data = mem.load_store()
    assert len(data["entries"]) == 2
