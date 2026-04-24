from __future__ import annotations

import json
from pathlib import Path


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def validate_lora2(rows):
    required = {"topic", "slide_goal", "asset_type", "layout_code", "placement"}
    for idx, row in enumerate(rows, start=1):
        missing = required - set(row.keys())
        if missing:
            raise ValueError(f"lora2 row {idx} missing fields: {sorted(missing)}")


def validate_lora3(rows):
    for idx, row in enumerate(rows, start=1):
        has_generation = {"planning_spec", "visual_assets_layout_code", "python_code"}.issubset(row.keys())
        has_repair = {"failed_code", "traceback", "repaired_code"}.issubset(row.keys())
        if not (has_generation or has_repair):
            raise ValueError(f"lora3 row {idx} invalid sample type")


def main():
    root = Path(__file__).resolve().parents[1]
    lora2 = load_jsonl(root / "data" / "samples" / "lora2_sample.jsonl")
    lora3 = load_jsonl(root / "data" / "samples" / "lora3_sample.jsonl")
    validate_lora2(lora2)
    validate_lora3(lora3)
    print("training data validation: OK")


if __name__ == "__main__":
    main()
