"""Structured service log helpers for dashboard-side runtime components."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def service_logs_root() -> Path:
    env_logs_dir = os.environ.get("ENGINE_LOGS_DIR")
    if env_logs_dir:
        return Path(env_logs_dir) / "service"
    return Path(__file__).parent.parent / "logs" / "service"


def append_service_log(
    service: str,
    level: str,
    message: str,
    *,
    kind: str = "service_event",
    **fields: Any,
) -> Path:
    log_dir = service_logs_root()
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "service": service,
        "kind": kind,
        "message": message,
        **fields,
    }
    log_file = log_dir / f"{service}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_file
