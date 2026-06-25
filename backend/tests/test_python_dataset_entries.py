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
