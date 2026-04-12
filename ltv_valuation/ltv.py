from __future__ import annotations

import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LOAN_PROGRAM_MAP = json.loads((DATA_DIR / "loan_program_ltv.json").read_text())["Program"]
SERVICE_AREA_DATA = json.loads((DATA_DIR / "service_area_ltv.json").read_text())


def get_program_ltv(program_name: str) -> float | None:
    raw = LOAN_PROGRAM_MAP.get(program_name)
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return raw / 100 if raw > 1 else float(raw)
    parsed = float(str(raw).replace("%", "").strip())
    return parsed / 100 if parsed > 1 else parsed


def get_service_area_ltv(zipcode: str | None):
    if not zipcode:
        return None
    digits = "".join(ch for ch in zipcode if ch.isdigit())[:5]
    for entry in SERVICE_AREA_DATA:
        if entry["Zip"] == digits:
            return entry
    return None
