from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SESSION_DIR = Path(__file__).resolve().parents[3] / "data" / "dataset_repair_sessions"
STORE_VERSION = 1
MAX_TURNS_PER_SESSION = 50
MAX_TURN_EXCERPT_CHARS = 1200
MAX_PROMPT_TURNS_IN_REPAIR = 12
MAX_SESSION_MEMORY_CHARS = 8000


@dataclass
class RepairSessionTurn:
    attempt: int
    error_type: str
    traceback: str
    repair_target: Optional[str] = None
    failure_kind: Optional[str] = None
    failed_python_excerpt: str = ""
    recorded_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt": self.attempt,
            "error_type": self.error_type,
            "traceback": self.traceback,
            "repair_target": self.repair_target,
            "failure_kind": self.failure_kind,
            "failed_python_excerpt": self.failed_python_excerpt,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RepairSessionTurn:
        return cls(
            attempt=int(data.get("attempt", 0)),
            error_type=str(data.get("error_type", "UnknownError")),
            traceback=str(data.get("traceback", "")),
            repair_target=data.get("repair_target"),
            failure_kind=data.get("failure_kind"),
            failed_python_excerpt=str(data.get("failed_python_excerpt", "")),
            recorded_at=str(data.get("recorded_at", "")),
        )


@dataclass
class RepairSession:
    prompt_key: str
    raw_prompt_excerpt: str
    turns: List[RepairSessionTurn] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": STORE_VERSION,
            "prompt_key": self.prompt_key,
            "raw_prompt_excerpt": self.raw_prompt_excerpt,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RepairSession:
        turns_raw = data.get("turns", [])
        turns: List[RepairSessionTurn] = []
        if isinstance(turns_raw, list):
            for item in turns_raw:
                if isinstance(item, dict):
                    turns.append(RepairSessionTurn.from_dict(item))
        return cls(
            prompt_key=str(data.get("prompt_key", "")),
            raw_prompt_excerpt=str(data.get("raw_prompt_excerpt", "")),
            turns=turns,
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _excerpt(text: str, max_chars: int) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _session_path(prompt_key: str) -> Path:
    safe_key = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in prompt_key)
    return SESSION_DIR / f"{safe_key}.json"


def _ensure_session_dir() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def load_repair_session(prompt_key: str) -> RepairSession:
    path = _session_path(prompt_key)
    if not path.exists():
        return RepairSession(prompt_key=prompt_key, raw_prompt_excerpt="")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return RepairSession(prompt_key=prompt_key, raw_prompt_excerpt="")
    if not isinstance(data, dict):
        return RepairSession(prompt_key=prompt_key, raw_prompt_excerpt="")
    session = RepairSession.from_dict(data)
    session.prompt_key = prompt_key
    return session


def save_repair_session(session: RepairSession) -> None:
    _ensure_session_dir()
    path = _session_path(session.prompt_key)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def clear_repair_session(prompt_key: str) -> None:
    path = _session_path(prompt_key)
    if path.exists():
        path.unlink(missing_ok=True)


def record_repair_session_error(
    session: RepairSession,
    *,
    raw_prompt: str,
    attempt: int,
    error_type: str,
    traceback_text: str,
    repair_target: Optional[str] = None,
    failure_kind: Optional[str] = None,
    failed_python_code: str = "",
) -> None:
    if not session.raw_prompt_excerpt:
        session.raw_prompt_excerpt = _excerpt(raw_prompt, 240)
    session.turns.append(
        RepairSessionTurn(
            attempt=attempt,
            error_type=(error_type or "UnknownError").strip() or "UnknownError",
            traceback=_excerpt(traceback_text, MAX_TURN_EXCERPT_CHARS),
            repair_target=repair_target,
            failure_kind=failure_kind,
            failed_python_excerpt=_excerpt(failed_python_code, MAX_TURN_EXCERPT_CHARS),
            recorded_at=_utc_now_iso(),
        )
    )
    if len(session.turns) > MAX_TURNS_PER_SESSION:
        session.turns = session.turns[-MAX_TURNS_PER_SESSION:]
    save_repair_session(session)


def format_session_memory_for_prompt(
    session: RepairSession,
    *,
    max_turns: int = MAX_PROMPT_TURNS_IN_REPAIR,
    total_max_chars: int = MAX_SESSION_MEMORY_CHARS,
) -> str:
    if not session.turns:
        return ""

    lines: List[str] = [
        "## MANDATORY — Repair session history for this exact prompt (errors only)",
        "",
        "These are prior failed attempts while fixing the same raw prompt in this workspace.",
        "Use them to avoid repeating the same mistake. Each turn includes the error and what was tried.",
        "",
    ]
    if session.raw_prompt_excerpt:
        lines.append(f"Prompt excerpt: {session.raw_prompt_excerpt}")
        lines.append("")

    for turn in session.turns[-max_turns:]:
        lines.append(f"### Attempt {turn.attempt} · {turn.error_type}")
        if turn.repair_target:
            lines.append(f"- repair_target: {turn.repair_target}")
        if turn.failure_kind:
            lines.append(f"- failure_kind: {turn.failure_kind}")
        if turn.traceback:
            lines.append(f"- traceback: {turn.traceback}")
        if turn.failed_python_excerpt:
            lines.append(f"- failed_python_excerpt: {turn.failed_python_excerpt}")
        lines.append("")

    text = "\n".join(lines).strip()
    if len(text) > total_max_chars:
        return text[: total_max_chars - 3] + "..."
    return text


def merge_repair_memory_addons(*parts: Optional[str]) -> str:
    blocks = [(part or "").strip() for part in parts if (part or "").strip()]
    return "\n\n---\n\n".join(blocks)
