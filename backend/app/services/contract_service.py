from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from jsonschema import validate


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "pipeline.contract.v1.json"


def validate_pipeline_contract(payload: Dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(instance=payload, schema=schema)
