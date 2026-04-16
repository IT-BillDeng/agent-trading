"""Helpers for canonical strategist artifact storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import append_jsonl, resolve_artifacts_root


def resolve_strategist_dir(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir) / "strategist"


def strategist_paths(base_dir: str | Path | None = None) -> dict[str, Path]:
    root = resolve_strategist_dir(base_dir)
    memory_dir = root / "memory"
    iterations_dir = root / "iterations"
    experiments_dir = root / "experiments"
    return {
        "root": root,
        "memory_dir": memory_dir,
        "iterations_dir": iterations_dir,
        "experiments_dir": experiments_dir,
        "strategy_plan_latest": root / "strategy_plan_latest.json",
        "strategy_plan_history": root / "strategy_plan_history.jsonl",
        "memory_latest": memory_dir / "latest.json",
        "memory_history": memory_dir / "history.jsonl",
        "proposals": root / "proposals.jsonl",
        "rejections": root / "rejections.jsonl",
        "code_change_proposals": root / "code_change_proposals.jsonl",
        "code_change_results": root / "code_change_results.jsonl",
        "rollback_notes": root / "rollback_notes.jsonl",
    }


def ensure_strategist_dirs(base_dir: str | Path | None = None) -> dict[str, Path]:
    paths = strategist_paths(base_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["memory_dir"].mkdir(parents=True, exist_ok=True)
    paths["iterations_dir"].mkdir(parents=True, exist_ok=True)
    paths["experiments_dir"].mkdir(parents=True, exist_ok=True)
    return paths


def record_code_change_proposal(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["code_change_proposals"], record)
    return paths["code_change_proposals"]


def record_code_change_result(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["code_change_results"], record)
    return paths["code_change_results"]


def record_rollback_note(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["rollback_notes"], record)
    return paths["rollback_notes"]
