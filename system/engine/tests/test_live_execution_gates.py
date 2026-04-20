from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.live_execution import LiveExecutionAdapter

from helpers import FakeBrokerClient


def _sample_intent():
    return {
        "intent_id": "intent-1",
        "idempotency_key": "idem-1",
        "symbol": "AAPL",
        "market": "US",
        "order_type": "LMT",
        "side": "BUY",
        "quantity": 1,
        "tif": "DAY",
        "limit_price": 100.0,
    }


def _sample_contracts():
    return {
        "US": {
            "AAPL": {
                "currency": "USD",
                "secType": "STK",
                "primaryExchange": "NASDAQ",
                "localSymbol": "AAPL",
            }
        }
    }


def _write_control_state(
    path: Path,
    *,
    mode: str = "paper_trade",
    enabled: bool = True,
    locked: bool = False,
    symbol_payload: dict | None = None,
    risk_payload: dict | None = None,
    live_readiness: dict | None = None,
):
    if mode == "live_trade" and live_readiness is None:
        live_readiness = {
            "checklist_id": "live-readiness-v1",
            "status": "ready",
            "confirm_live": True,
            "items": {
                "p0_safety_tests_passed": True,
                "p1_risk_tests_passed": True,
                "paper_shadow_20d_stable": True,
                "fee_model_confidence_ok": True,
                "recent_data_health_ok": True,
                "broker_no_unknown_open_orders": True,
                "execution_state_reconciled": True,
                "operator_confirmed": True,
            },
            "failed_items": [],
        }
    payload = {
        "locked": locked,
        "global": {"enabled": enabled, "mode": mode},
        "markets": {"US": True},
        "symbols": symbol_payload or {},
        "risk": {
            "reduce_only": False,
            "emergency_flatten": False,
            "daily_loss_locked": False,
        },
        "live_readiness": live_readiness,
        "history": [],
    }
    if risk_payload:
        payload["risk"].update(risk_payload)
    (path / "control_state.json").write_text(json.dumps(payload, ensure_ascii=False))


class LiveExecutionGateTests(unittest.TestCase):
    def test_guarded_defaults_never_call_place_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(state_dir, mode="paper_trade")
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "paper",
                    "execution": {
                        "submit_mode": "guarded",
                        "live_submit": False,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "app_mode:paper")
            self.assertEqual(client.preview_order_called, 1)
            self.assertEqual(client.place_order_called, 0)

    def test_live_mode_with_guarded_submit_mode_never_calls_place_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(state_dir, mode="live_trade")
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "guarded",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "guarded_mode")
            self.assertEqual(client.place_order_called, 0)

    def test_live_mode_and_live_submit_still_block_when_control_not_live_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(state_dir, mode="paper_trade")
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "control_mode:paper_trade")
            self.assertEqual(client.place_order_called, 0)

    def test_all_live_conditions_must_be_met_before_place_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(state_dir, mode="live_trade")
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertTrue(result.submitted)
            self.assertEqual(result.reason, "submitted")
            self.assertEqual(client.place_order_called, 1)

    def test_reduce_only_blocks_buy_live_submit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(
                state_dir,
                mode="live_trade",
                risk_payload={"reduce_only": True},
            )
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "risk_reduce_only")
            self.assertEqual(client.place_order_called, 0)

    def test_live_trade_without_ready_readiness_never_submits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(
                state_dir,
                mode="live_trade",
                live_readiness={
                    "checklist_id": "live-readiness-v1",
                    "status": "missing",
                    "confirm_live": False,
                    "items": {},
                    "failed_items": ["operator_confirmed"],
                },
            )
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "live_readiness:missing")
            self.assertEqual(client.place_order_called, 0)

    def test_daily_loss_locked_blocks_buy_live_submit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            _write_control_state(
                state_dir,
                mode="live_trade",
                risk_payload={"daily_loss_locked": True},
            )
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "risk_daily_loss_locked")
            self.assertEqual(client.place_order_called, 0)

    def test_locked_control_blocks_submit_before_preview_or_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_control_state(Path(tmpdir), mode="live_trade")
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )
            adapter.control.lock("manual safety test", updated_by="test")

            result = adapter.submit_intent(_sample_intent(), _sample_contracts())

            self.assertFalse(result.submitted)
            self.assertIn("lock", result.reason)
            self.assertEqual(client.preview_order_called, 0)
            self.assertEqual(client.place_order_called, 0)

    def test_cancel_order_blocks_when_live_cancel_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_control_state(Path(tmpdir), mode="live_trade")
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
                    "mode": "live",
                    "execution": {
                        "submit_mode": "live",
                        "live_submit": True,
                        "live_cancel": False,
                        "preview_check": True,
                    },
                    "system": {
                        "state_dir": tmpdir,
                    },
                },
                client,
            )

            result = adapter.cancel_order("order-1", order_id=1001)

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "guarded_cancel_mode")
            self.assertEqual(client.cancel_order_called, 0)


if __name__ == "__main__":
    unittest.main()
