from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import append_jsonl, resolve_artifacts_root


def resolve_broker_dir(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir) / "broker"


def record_fee_calibration(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    broker_dir = resolve_broker_dir(base_dir)
    output = broker_dir / "fee_calibration.jsonl"
    append_jsonl(output, record)
    return output
