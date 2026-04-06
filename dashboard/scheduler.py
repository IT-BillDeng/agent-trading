"""Background scheduler — periodically runs engine signal generation."""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SignalScheduler:
    """Runs engine signal generation on a configurable interval."""

    def __init__(
        self,
        app_config_path: str,
        runtime_dir: str,
        provider_name: str = "yfinance",
        interval_seconds: int = 60,
    ):
        self._app_config_path = Path(app_config_path)
        self._runtime_dir = Path(runtime_dir)
        self._provider_name = provider_name
        self._interval = interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._state = {
            "running": False,
            "last_cycle": None,
            "last_cycle_time": None,
            "cycle_count": 0,
            "errors": [],
        }
        # Ensure runtime dirs exist
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        (self._runtime_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self._runtime_dir / "state").mkdir(parents=True, exist_ok=True)

    def start(self):
        """Start the background scheduler."""
        if self._thread and self._thread.is_alive():
            logger.warning("Scheduler already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._state["running"] = True
        logger.info(f"Scheduler started (interval={self._interval}s, provider={self._provider_name})")

    def stop(self):
        """Stop the background scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._state["running"] = False
        logger.info("Scheduler stopped")

    def get_state(self) -> dict[str, Any]:
        """Get scheduler state."""
        with self._lock:
            return dict(self._state)

    def set_interval(self, seconds: int):
        """Update the polling interval."""
        if seconds < 10:
            seconds = 10
        self._interval = seconds
        logger.info(f"Scheduler interval set to {seconds}s")

    def _loop(self):
        """Main loop — run engine cycle periodically."""
        while not self._stop_event.is_set():
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"Scheduler cycle error: {e}")
                with self._lock:
                    self._state["errors"].append({
                        "time": datetime.now().isoformat(),
                        "error": str(e),
                    })
                    # Keep only last 20 errors
                    if len(self._state["errors"]) > 20:
                        self._state["errors"] = self._state["errors"][-20:]
            self._stop_event.wait(self._interval)

    def _check_trading_mode(self) -> bool:
        """Check if signal generation is enabled."""
        state_file = self._runtime_dir / "state" / "control_state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                mode = state.get("trading_mode", "off")
                if mode == "off":
                    return False
                if state.get("locked", False):
                    return False
                return True
            except Exception:
                pass
        # Default: allow signals if no control state exists
        return True

    def _get_trading_mode(self) -> str:
        """Get current trading mode."""
        state_file = self._runtime_dir / "state" / "control_state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                return state.get("trading_mode", "off")
            except Exception:
                pass
        return "off"

    def _run_cycle(self):
        """Execute one engine cycle."""
        # Check trading mode
        if not self._check_trading_mode():
            logger.debug("Trading mode is off or locked, skipping cycle")
            return

        mode = self._get_trading_mode()

        # Lazy imports to avoid circular dependencies
        import sys
        engine_src = str(Path(__file__).parent.parent / "system" / "tiger_engine" / "src")
        if engine_src not in sys.path:
            sys.path.insert(0, engine_src)

        from tiger_engine.config import load_app_config
        from tiger_engine.data_provider import create_data_provider
        from tiger_engine.runtime import (
            fetch_cycle_raw_with_provider,
            build_strategy_summary,
            build_execution_summary,
        )

        # Load config
        if not self._app_config_path.exists():
            logger.error(f"Config not found: {self._app_config_path}")
            return

        app = load_app_config(str(self._app_config_path))

        # Create data provider (yfinance or tiger)
        provider = create_data_provider(self._provider_name)

        # Fetch data
        raw = fetch_cycle_raw_with_provider(client=None, data=provider, app=app)

        # Build summary based on mode
        if mode == "signals":
            # Signals only — skip risk/execution
            summary = build_strategy_summary(raw, app)
        else:
            # paper/live — full execution pipeline
            # Dynamically set live_submit based on mode
            if mode == "paper":
                app.raw.setdefault("execution", {})["live_submit"] = False
            elif mode == "live":
                app.raw.setdefault("execution", {})["live_submit"] = True

            summary = build_execution_summary(raw, app)

            # Submit orders if paper or live mode
            if mode in ("paper", "live"):
                self._submit_orders(summary, app)

        # Add cycle metadata
        summary["cycle_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary["scheduler_provider"] = self._provider_name
        summary["trading_mode"] = mode

        # Write to runtime (same file the dashboard API reads)
        cycle_file = self._runtime_dir / ".last_execution_cycle.json"
        cycle_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

        # Update state
        with self._lock:
            self._state["last_cycle"] = summary.get("cycle_id")
            self._state["last_cycle_time"] = datetime.now().isoformat()
            self._state["cycle_count"] += 1

        # Log signals
        signals = summary.get("strategy", {}).get("signals", [])
        for s in signals:
            logger.info(f"Signal: {s.get('action')} {s.get('symbol')} (confidence={s.get('confidence')})")

        # Log order submissions
        if "execution_submit" in summary:
            for item in summary["execution_submit"].get("items", []):
                status = "SUBMITTED" if item.get("submitted") else f"BLOCKED({item.get('reason')})"
                logger.info(f"Order: {item.get('symbol')} {status}")

    def _submit_orders(self, summary: dict, app):
        """Preview and submit orders via Tiger API."""
        try:
            from tiger_engine.tiger_client import TigerClient
            from tiger_engine.config import load_tiger_props
            from tiger_engine.live_execution import LiveExecutionAdapter
            from tiger_engine.control import ControlPlane

            # Load Tiger credentials
            config_dir = self._app_config_path.parent
            props_file = config_dir / "tiger_openapi_config.properties"
            if not props_file.exists():
                logger.warning("Tiger credentials not found, skipping order submission")
                summary["execution_submit"] = {"items": [], "count": 0, "error": "no_credentials"}
                return

            props = load_tiger_props(str(props_file))
            client = TigerClient(props)
            adapter = LiveExecutionAdapter(app.raw, client)
            control = ControlPlane(str(self._runtime_dir / "state"))

            intents = summary.get("order_intents", {}).get("items", [])
            contracts = summary.get("contracts", {})

            if not intents:
                summary["execution_submit"] = {"items": [], "count": 0}
                return

            # Preview
            preview_results = [item.to_dict() for item in adapter.preview_intents(intents, contracts)]
            summary["execution_preview_check"] = {
                "items": preview_results,
                "count": len(preview_results),
            }
            summary.setdefault("risk", {})["preview_blockers"] = [
                {"intent_id": p.get("intent_id"), "symbol": p.get("symbol"),
                 "reason": p.get("reason"), "warning_text": p.get("warning_text")}
                for p in preview_results if not p.get("ok")
            ]

            # Submit
            gate_ok, gate_reason = control.can_trade()
            if not gate_ok:
                submit_results = [
                    {"intent_id": i.get("intent_id"), "symbol": i.get("symbol"),
                     "submitted": False, "reason": gate_reason, "response": None}
                    for i in intents
                ]
            else:
                submit_results = [item.to_dict() for item in adapter.submit_intents(intents, contracts)]

            summary["execution_submit"] = {
                "items": submit_results,
                "count": len(submit_results),
                "mode": app.raw.get("execution", {}).get("submit_mode", "guarded"),
            }

        except Exception as e:
            logger.error(f"Order submission error: {e}")
            summary["execution_submit"] = {"items": [], "count": 0, "error": str(e)}
