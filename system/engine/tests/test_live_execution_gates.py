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


class LiveExecutionGateTests(unittest.TestCase):
    def test_guarded_defaults_never_call_place_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            (state_dir / "control_state.json").write_text(
                json.dumps(
                    {
                        "locked": False,
                        "global": {"enabled": True, "mode": "paper_trade"},
                        "markets": {"US": True},
                        "symbols": {},
                        "risk": {
                            "reduce_only": False,
                            "emergency_flatten": False,
                            "daily_loss_locked": False,
                        },
                        "history": [],
                    },
                    ensure_ascii=False,
                )
            )
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
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
            self.assertEqual(result.reason, "guarded_mode")
            self.assertEqual(client.preview_order_called, 1)
            self.assertEqual(client.place_order_called, 0)

    def test_locked_control_blocks_submit_before_preview_or_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = FakeBrokerClient()
            adapter = LiveExecutionAdapter(
                {
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


if __name__ == "__main__":
    unittest.main()
