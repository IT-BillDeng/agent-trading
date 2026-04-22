from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..artifacts import append_jsonl, resolve_artifacts_root, write_json


def resolve_factor_artifacts_dir(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir) / "factors"


class FactorStore:
    def __init__(self, base_dir: str | Path | None = None, *, artifacts_dir: str | Path | None = None):
        if artifacts_dir is not None:
            self.artifacts_dir = Path(artifacts_dir)
        else:
            self.artifacts_dir = resolve_factor_artifacts_dir(base_dir)

    def write_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Path]:
        latest_path = self.artifacts_dir / "latest.json"
        history_path = self.artifacts_dir / "history" / f"{self._snapshot_date(snapshot)}.jsonl"
        write_json(latest_path, snapshot)
        append_jsonl(history_path, snapshot)
        return {
            "latest": latest_path,
            "history": history_path,
        }

    def _snapshot_date(self, snapshot: dict[str, Any]) -> str:
        timestamp = snapshot.get("timestamp")
        if timestamp:
            text = str(timestamp)
            if "T" in text:
                return text.split("T", 1)[0]
            if " " in text:
                return text.split(" ", 1)[0]
            return text[:10]
        return datetime.now(timezone.utc).date().isoformat()
