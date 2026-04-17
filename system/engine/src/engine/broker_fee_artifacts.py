from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import append_jsonl, resolve_artifacts_root, write_json


def resolve_broker_dir(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir) / "broker"


def classify_fee_calibration_trust(*, avg_delta: float, max_abs_delta: float, count: int) -> dict[str, str]:
    if count < 3:
        return {
            "level": "observe",
            "label": "观察",
            "reason": "真实费用记录不足",
        }
    if max_abs_delta >= 1.0 or abs(avg_delta) >= 0.5:
        return {
            "level": "low",
            "label": "不可信",
            "reason": "近期费用估算偏差较大",
        }
    if max_abs_delta >= 0.3 or abs(avg_delta) >= 0.15:
        return {
            "level": "observe",
            "label": "观察",
            "reason": "费用模型存在中等偏差",
        }
    return {
        "level": "high",
        "label": "可信",
        "reason": "近期费用估算偏差可接受",
    }


def summarize_fee_calibration(base_dir: str | Path | None = None, *, limit: int = 20) -> dict[str, Any]:
    broker_dir = resolve_broker_dir(base_dir)
    records_file = broker_dir / "fee_calibration.jsonl"
    entries: list[dict[str, Any]] = []
    if records_file.exists():
        for line in records_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                entries.append(payload)

    recent = entries[-limit:]
    avg_delta = (
        sum(float(item.get("delta", 0) or 0) for item in recent) / len(recent)
        if recent else 0.0
    )
    max_abs_delta = max(
        (abs(float(item.get("delta", 0) or 0)) for item in recent),
        default=0.0,
    )
    trust = classify_fee_calibration_trust(
        avg_delta=avg_delta,
        max_abs_delta=max_abs_delta,
        count=len(recent),
    )
    summary = {
        "count": len(recent),
        "avg_delta": round(avg_delta, 6),
        "max_abs_delta": round(max_abs_delta, 6),
        "trust": trust,
        "recent": recent[-8:][::-1],
    }
    write_json(broker_dir / "fee_calibration_summary.json", summary)
    return summary


def record_fee_calibration(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    broker_dir = resolve_broker_dir(base_dir)
    output = broker_dir / "fee_calibration.jsonl"
    append_jsonl(output, record)
    summarize_fee_calibration(base_dir)
    return output
