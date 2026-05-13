from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ERROR_MEMORY_FILE = Path(__file__).resolve().parents[3] / "data" / "pptx_error_memory.json"

STORE_VERSION = 1
MAX_STORE_ENTRIES = 200
DEFAULT_PROMPT_MAX_ITEMS = 10
DEFAULT_EXCERPT_MAX_CHARS = 400
DEFAULT_PROMPT_TOTAL_MAX_CHARS = 6000

_FINGERPRINT_TAIL_LINES = 40
# Drive letter paths: require at least one path segment (avoid matching bare "D:\" only).
_PATH_WINDOWS = re.compile(r"[A-Za-z]:\\[^\s,\"']+")
_PATH_UNIXLIKE = re.compile(r"(?:/[^\s:,\"']{1,240})+")
_WHITESPACE = re.compile(r"\s+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_traceback_for_fingerprint(traceback_text: str) -> str:
    text = (traceback_text or "").strip()
    if not text:
        return ""
    text = _PATH_WINDOWS.sub("<PATH>", text)
    text = _PATH_UNIXLIKE.sub("<PATH>", text)
    text = _WHITESPACE.sub(" ", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-_FINGERPRINT_TAIL_LINES:] if len(lines) > _FINGERPRINT_TAIL_LINES else lines
    return "\n".join(tail)


def _fingerprint(error_type: str, normalized: str) -> str:
    payload = f"{error_type}\n{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summary_line(normalized: str, raw: str) -> str:
    if normalized:
        lines = [ln.strip() for ln in normalized.splitlines() if ln.strip()]
        if lines:
            return lines[-1][:500]
    first = (raw or "").strip().splitlines()
    if first:
        return first[0][:500]
    return "Unknown error"


def _excerpt(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3] + "..."


def _ensure_data_dir() -> None:
    ERROR_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_store() -> Dict[str, Any]:
    if not ERROR_MEMORY_FILE.exists():
        return {"version": STORE_VERSION, "entries": []}
    try:
        raw = ERROR_MEMORY_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {"version": STORE_VERSION, "entries": []}
    if not isinstance(data, dict):
        return {"version": STORE_VERSION, "entries": []}
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {"version": int(data.get("version", STORE_VERSION)), "entries": entries}


def _save_store(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    temp = ERROR_MEMORY_FILE.with_suffix(ERROR_MEMORY_FILE.suffix + ".tmp")
    payload = json.dumps(
        {"version": STORE_VERSION, "entries": data.get("entries", [])},
        ensure_ascii=False,
        indent=2,
    )
    temp.write_text(payload + "\n", encoding="utf-8")
    temp.replace(ERROR_MEMORY_FILE)


def _prune_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(entries) <= MAX_STORE_ENTRIES:
        return entries

    def sort_key(e: Dict[str, Any]) -> Tuple[int, str]:
        count = int(e.get("occurrence_count", 1))
        last = str(e.get("last_seen_at", ""))
        return (count, last)

    sorted_entries = sorted(entries, key=sort_key)
    drop = len(entries) - MAX_STORE_ENTRIES
    return sorted_entries[drop:]


def record_error(*, error_type: Optional[str], traceback_text: str) -> None:
    et = (error_type or "UnknownError").strip() or "UnknownError"
    raw_tb = traceback_text or ""
    normalized = normalize_traceback_for_fingerprint(raw_tb)
    if not normalized and not raw_tb.strip():
        return
    fp = _fingerprint(et, normalized)
    summary = _summary_line(normalized, raw_tb)
    excerpt = _excerpt(raw_tb if raw_tb.strip() else normalized, DEFAULT_EXCERPT_MAX_CHARS * 2)

    data = load_store()
    entries: List[Dict[str, Any]] = [e for e in data.get("entries", []) if isinstance(e, dict)]
    now = _utc_now_iso()

    for e in entries:
        if e.get("fingerprint") == fp:
            e["occurrence_count"] = int(e.get("occurrence_count", 1)) + 1
            e["last_seen_at"] = now
            e["summary"] = summary
            e["representative_excerpt"] = excerpt
            _save_store({"entries": _prune_entries(entries)})
            return

    entries.append(
        {
            "fingerprint": fp,
            "error_type": et,
            "summary": summary,
            "representative_excerpt": excerpt,
            "occurrence_count": 1,
            "first_seen_at": now,
            "last_seen_at": now,
        }
    )
    _save_store({"entries": _prune_entries(entries)})


def format_error_memory_for_prompt(
    *,
    max_items: int = DEFAULT_PROMPT_MAX_ITEMS,
    excerpt_max_chars: int = DEFAULT_EXCERPT_MAX_CHARS,
    total_max_chars: int = DEFAULT_PROMPT_TOTAL_MAX_CHARS,
) -> str:
    data = load_store()
    entries: List[Dict[str, Any]] = [e for e in data.get("entries", []) if isinstance(e, dict)]
    if not entries:
        return ""

    def sort_key(e: Dict[str, Any]) -> Tuple[int, str]:
        return (-int(e.get("occurrence_count", 1)), str(e.get("last_seen_at", "")))

    entries = sorted(entries, key=sort_key)[:max_items]

    lines: List[str] = [
        "## MANDATORY — PPTX / python-pptx error memory (must not recur)",
        "",
        "These lines summarize **real failures** already seen in this workspace (execution, parsing, or generation).",
        "Compliance rules:",
        "- Treat every item as a **hard constraint**: your Thinking plan and Assistant Python must **not** reproduce the same root cause, API misuse, or traceback pattern.",
        "- Prefer defensive patterns (e.g. guard `slide.shapes.title`, valid chart enums, layout indices, file output) implied by the messages below.",
        "- Higher occurrence counts indicate recurring mistakes — prioritize avoiding those first.",
        "",
        "### Logged failures (newest / most frequent first)",
        "",
    ]
    for i, e in enumerate(entries, start=1):
        et = str(e.get("error_type", "Error"))
        summary = str(e.get("summary", ""))
        count = int(e.get("occurrence_count", 1))
        excerpt = _excerpt(str(e.get("representative_excerpt", "")), excerpt_max_chars)
        lines.append(f"{i}. **[{et}]** ×{count} — {summary}")
        if excerpt:
            lines.append(f"   Evidence (do **not** reproduce): {excerpt}")
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > total_max_chars:
        return text[: total_max_chars - 3] + "..."
    return text
