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

    def _run_cycle(self):
        """Execute one engine cycle."""
        # Lazy imports to avoid circular dependencies
        import sys
        engine_src = str(Path(__file__).parent.parent / "system" / "tiger_engine" / "src")
        if engine_src not in sys.path:
            sys.path.insert(0, engine_src)

        from tiger_engine.config import load_app_config
        from tiger_engine.data_provider import create_data_provider
        from tiger_engine.runtime import fetch_cycle_raw_with_provider, build_strategy_summary

        # Load config
        if not self._app_config_path.exists():
            logger.error(f"Config not found: {self._app_config_path}")
            return

        app = load_app_config(str(self._app_config_path))

        # Create data provider (yfinance or tiger)
        provider = create_data_provider(self._provider_name)

        # Fetch data and build summary (no TigerClient — trade ops return empty)
        raw = fetch_cycle_raw_with_provider(client=None, data=provider, app=app)
        summary = build_strategy_summary(raw, app)

        # Add cycle metadata
        summary["cycle_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary["scheduler_provider"] = self._provider_name

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
        if signals:
            for s in signals:
                logger.info(f"Signal: {s.get('action')} {s.get('symbol')} (confidence={s.get('confidence')})")
        else:
            logger.debug("No signals generated")
