import json
from pathlib import Path

import pytest

from app.services import dataset_service as service


VALID_CODE = "from pptx import Presentation\nPresentation().save('output.pptx')"


def _configure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_dir = tmp_path / "datasets"
    monkeypatch.setattr(service, "DATASET_DIR", dataset_dir)
    monkeypatch.setattr(service, "PYTHON_ENTRY_DIR", dataset_dir / "python_entries")


def test_write_and_read_python_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    row = service.build_messages_row("make a deck", VALID_CODE, service.PYTHON_SYSTEM_PROMPT)

    path = service.write_python_entry("abc123", row)
    detail = service.read_python_entry(path.name)

    assert path.name == "abc123.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert detail["valid"] is True
    assert detail["row"] == row


def test_python_entry_validation_rejects_markdown_and_invalid_python():
    row = service.build_messages_row(
        "make a deck",
        "# Assistant\n```python\nif:\n```",
        service.PYTHON_SYSTEM_PROMPT,
    )
    valid, errors = service.validate_python_entry_row(row)

    assert valid is False
    assert any("Markdown" in error for error in errors)
    assert any("Python 문법 오류" in error for error in errors)


def test_list_python_entries_reports_invalid_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    service.PYTHON_ENTRY_DIR.mkdir(parents=True)
    (service.PYTHON_ENTRY_DIR / "broken.jsonl").write_text(
        json.dumps({"messages": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    entries = service.list_python_entries()

    assert len(entries) == 1
    assert entries[0]["filename"] == "broken.jsonl"
    assert entries[0]["valid"] is False
    assert entries[0]["errors"]


def test_read_python_entry_rejects_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="파일명"):
        service.read_python_entry("../outside.jsonl")


def test_merge_python_entries_writes_valid_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    row_a = service.build_messages_row("prompt a", VALID_CODE, service.PYTHON_SYSTEM_PROMPT)
    row_b = service.build_messages_row("prompt b", VALID_CODE, service.PYTHON_SYSTEM_PROMPT)
    service.write_python_entry("entry_a", row_a)
    service.write_python_entry("entry_b", row_b)

    result = service.merge_python_entries(["entry_a.jsonl", "entry_b.jsonl"], "merged_output.jsonl")

    output_path = service.DATASET_DIR / "merged_output.jsonl"
    assert result["filename"] == "merged_output.jsonl"
    assert result["record_count"] == 2
    assert result["skipped_invalid"] == []
    assert result["missing"] == []
    assert output_path.exists()
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == row_a
    assert json.loads(lines[1]) == row_b


def test_merge_python_entries_skips_invalid_and_reports_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    valid_row = service.build_messages_row("valid prompt", VALID_CODE, service.PYTHON_SYSTEM_PROMPT)
    service.write_python_entry("valid_entry", valid_row)
    service.PYTHON_ENTRY_DIR.mkdir(parents=True, exist_ok=True)
    (service.PYTHON_ENTRY_DIR / "broken.jsonl").write_text(
        json.dumps({"messages": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = service.merge_python_entries(
        ["valid_entry.jsonl", "broken.jsonl", "missing.jsonl"],
        "partial_merge.jsonl",
    )

    output_path = service.DATASET_DIR / "partial_merge.jsonl"
    assert result["record_count"] == 1
    assert result["skipped_invalid"] == ["broken.jsonl"]
    assert result["missing"] == ["missing.jsonl"]
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 1


def test_merge_python_entries_rejects_unsafe_output_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    row = service.build_messages_row("prompt", VALID_CODE, service.PYTHON_SYSTEM_PROMPT)
    service.write_python_entry("entry_one", row)

    with pytest.raises(ValueError, match="경로"):
        service.merge_python_entries(["entry_one.jsonl"], "../escape.jsonl")

    with pytest.raises(ValueError, match="보호"):
        service.merge_python_entries(["entry_one.jsonl"], "python_lora.jsonl")


def test_merge_python_entries_rejects_existing_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    row = service.build_messages_row("prompt", VALID_CODE, service.PYTHON_SYSTEM_PROMPT)
    service.write_python_entry("entry_one", row)
    existing = service.DATASET_DIR / "existing_merge.jsonl"
    existing.write_text("{}\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="existing_merge.jsonl"):
        service.merge_python_entries(["entry_one.jsonl"], "existing_merge.jsonl")


def test_merge_python_entries_raises_when_no_valid_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _configure_paths(tmp_path, monkeypatch)
    service.PYTHON_ENTRY_DIR.mkdir(parents=True, exist_ok=True)
    (service.PYTHON_ENTRY_DIR / "broken.jsonl").write_text(
        json.dumps({"messages": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="유효한 레코드"):
        service.merge_python_entries(["broken.jsonl"], "empty_merge.jsonl")
