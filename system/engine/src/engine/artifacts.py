"""Helpers for canonical agent artifact storage."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def resolve_artifacts_root(base_dir: str | Path | None = None) -> Path:
    env_artifacts_dir = (
        os.environ.get("ENGINE_ARTIFACTS_DIR")
        or os.environ.get("BROKER_ARTIFACTS_DIR")
        or os.environ.get("TIGER_ARTIFACTS_DIR")
    )
    if env_artifacts_dir:
        return Path(env_artifacts_dir)

    if base_dir is not None:
        base_path = Path(base_dir).resolve()
        if base_path.name == "engine" and len(base_path.parents) >= 2:
            return base_path.parents[1] / "artifacts"
        return base_path.parent / "artifacts"

    return Path(__file__).resolve().parents[4] / "artifacts"


def write_json(path: str | Path, data: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def append_jsonl(path: str | Path, record: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
