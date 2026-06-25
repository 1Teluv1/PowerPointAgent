from __future__ import annotations

from pathlib import Path

# backend/app/core/paths.py -> parents[3] == repository root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts"
TOOL_ARTIFACT_ROOT = ARTIFACT_ROOT / "tools"
