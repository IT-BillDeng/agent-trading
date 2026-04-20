from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi.responses import JSONResponse

from system.engine.src.engine.strategist_artifacts import (
    approve_request as approve_strategy_proposal,
    get_proposal_review_record,
    list_proposal_review_records,
    reject_request as reject_strategy_proposal,
)


_artifacts_root_getter: Callable[[], Path] = lambda: Path(".")


def set_proposal_artifacts_root_getter(getter: Callable[[], Path]) -> None:
    global _artifacts_root_getter
    _artifacts_root_getter = getter


def _proposal_artifacts_base_dir() -> Path:
    return _artifacts_root_getter()


async def api_strategy_proposals():
    try:
        return {
            "items": list_proposal_review_records(base_dir=_proposal_artifacts_base_dir()),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_strategy_proposal_detail(proposal_id: str):
    try:
        return get_proposal_review_record(proposal_id, base_dir=_proposal_artifacts_base_dir())
    except FileNotFoundError:
        return JSONResponse({"error": f"proposal not found: {proposal_id}"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_strategy_proposal_approve(proposal_id: str, body: dict | None = None):
    payload = body or {}
    decision_record = {
        "decider_type": payload.get("decider_type", "human"),
        "decider_id": payload.get("decider_id", "dashboard"),
    }
    if payload.get("reason") is not None:
        decision_record["reason"] = payload.get("reason")
    try:
        queue_path, decision_path = approve_strategy_proposal(
            proposal_id,
            decision_record,
            base_dir=_proposal_artifacts_base_dir(),
        )
        return {
            "status": "ok",
            "proposal_id": proposal_id,
            "decision": "approved",
            "queue_path": str(queue_path),
            "decision_path": str(decision_path),
        }
    except FileNotFoundError:
        return JSONResponse({"error": f"proposal not found: {proposal_id}"}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_strategy_proposal_reject(proposal_id: str, body: dict | None = None):
    payload = body or {}
    decision_record = {
        "decider_type": payload.get("decider_type", "human"),
        "decider_id": payload.get("decider_id", "dashboard"),
    }
    if payload.get("reason") is not None:
        decision_record["reason"] = payload.get("reason")
    try:
        queue_path, decision_path = reject_strategy_proposal(
            proposal_id,
            decision_record,
            base_dir=_proposal_artifacts_base_dir(),
        )
        return {
            "status": "ok",
            "proposal_id": proposal_id,
            "decision": "rejected",
            "queue_path": str(queue_path),
            "decision_path": str(decision_path),
        }
    except FileNotFoundError:
        return JSONResponse({"error": f"proposal not found: {proposal_id}"}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def register_proposal_routes(app) -> None:
    app.get("/api/strategy/proposals")(api_strategy_proposals)
    app.get("/api/strategy/proposals/{proposal_id}")(api_strategy_proposal_detail)
    app.post("/api/strategy/proposals/{proposal_id}/approve")(api_strategy_proposal_approve)
    app.post("/api/strategy/proposals/{proposal_id}/reject")(api_strategy_proposal_reject)
