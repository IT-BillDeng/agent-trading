import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "system" / "engine" / "src"))

from engine.intent import IntentBuilder
from engine.live_execution import LiveExecutionAdapter


def _response(order_snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "http_status": 200,
        "body": {
            "code": 0,
            "message": "success",
            "data": json.dumps(order_snapshot, ensure_ascii=False),
        },
    }


class FakeBrokerClient:
    def __init__(self, order_snapshot: dict[str, Any], transactions: Optional[list[dict[str, Any]]] = None):
        self._order_snapshot = order_snapshot
        self._transactions = transactions or []
        self.place_order_calls = 0

    @property
    def account(self) -> str:
        return "demo-account"

    def get_accounts(self) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}

    def get_assets(self) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}

    def get_positions(self) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"items": []}}}

    def get_active_orders(self) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"items": []}}}

    def get_inactive_orders(self, limit: int = 20) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"items": []}}}

    def get_filled_orders(self, limit: int = 20) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"items": []}}}

    def get_order(self, id: Optional[int] = None, order_id: Optional[int] = None, show_charges: bool = False) -> dict[str, Any]:
        return _response(self._order_snapshot)

    def get_transactions(self, order_id: Optional[int] = None, symbol: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"items": self._transactions}}}

    def get_market_state(self, market: str) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"market": market}}}

    def get_quote_permission(self) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}

    def get_delay_quotes(self, symbols: list[str], market: Optional[str] = None) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}

    def get_briefs(self, symbols: list[str], market: Optional[str] = None) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}

    def get_bars(self, symbols: list[str], period: str = "30min", limit: int = 30, begin_time: Optional[str] = None, end_time: Optional[str] = None) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": []}}

    def get_contract(self, symbol: str, market: str) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}

    def create_order_no(self) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": 999}}

    def preview_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {"isPass": True}}}

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.place_order_calls += 1
        return {"http_status": 200, "body": {"code": 0, "message": "success", "data": {"order_id": payload.get("order_id", 999)}}}

    def cancel_order(self, id: Optional[int] = None, order_id: Optional[int] = None) -> dict[str, Any]:
        return {"http_status": 200, "body": {"code": 0, "data": {}}}


class LiveExecutionIdempotencyTests(unittest.TestCase):
    def _make_adapter(self, fake_client: FakeBrokerClient, state_dir: Path) -> LiveExecutionAdapter:
        app_config = {
            "mode": "live",
            "execution": {
                "submit_mode": "live",
                "live_submit": True,
                "preview_check": False,
            },
            "system": {
                "state_dir": str(state_dir),
            },
        }
        return LiveExecutionAdapter(app_config, fake_client)

    def _build_intent(self, symbol: str, side: str, quantity: int, order_type: str = "MKT") -> dict[str, Any]:
        preview = {
            "market": "US",
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "limit_price": None,
            "stop_price": None,
            "tif": "DAY",
        }
        intent = IntentBuilder({"mode": "live"}).build([preview], cycle_id="cycle-1")[0]
        return intent.to_dict()

    def test_duplicate_active_submission_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            fake_client = FakeBrokerClient(
                {
                    "id": 111,
                    "orderId": 146,
                    "status": "Initial",
                    "totalQuantity": 15,
                    "filledQuantity": 0,
                    "remainingQuantity": 15,
                    "orderType": "MKT",
                    "action": "SELL",
                }
            )
            adapter = self._make_adapter(fake_client, state_dir)
            intent = self._build_intent("AAPL", "SELL", 15)
            adapter.state.mark_submitted(intent["idempotency_key"], {
                "intent_id": intent["intent_id"],
                "symbol": intent["symbol"],
                "payload": {"order_id": 146},
                "response": _response({
                    "id": 111,
                    "order_id": 146,
                    "status": "Initial",
                    "totalQuantity": 15,
                    "filledQuantity": 0,
                    "remainingQuantity": 15,
                    "orderType": "MKT",
                    "action": "SELL",
                }),
            })

            result = adapter.submit_intent(intent, contracts={})

            self.assertFalse(result.submitted)
            self.assertEqual(result.reason, "duplicate_active_submission")
            self.assertEqual(fake_client.place_order_calls, 0)

    def test_terminal_submission_can_be_resubmitted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            fake_client = FakeBrokerClient(
                {
                    "id": 222,
                    "orderId": 146,
                    "status": "Filled",
                    "totalQuantity": 15,
                    "filledQuantity": 15,
                    "remainingQuantity": 0,
                    "orderType": "MKT",
                    "action": "SELL",
                }
            )
            adapter = self._make_adapter(fake_client, state_dir)
            intent = self._build_intent("AAPL", "SELL", 15)
            adapter.state.mark_submitted(intent["idempotency_key"], {
                "intent_id": intent["intent_id"],
                "symbol": intent["symbol"],
                "payload": {"order_id": 146},
                "response": _response({
                    "id": 222,
                    "order_id": 146,
                    "status": "Filled",
                    "totalQuantity": 15,
                    "filledQuantity": 15,
                    "remainingQuantity": 0,
                    "orderType": "MKT",
                    "action": "SELL",
                }),
            })

            result = adapter.submit_intent(intent, contracts={})

            self.assertTrue(result.submitted)
            self.assertEqual(result.reason, "submitted")
            self.assertEqual(fake_client.place_order_calls, 1)


if __name__ == "__main__":
    unittest.main()
