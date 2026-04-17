import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_SRC = Path(__file__).resolve().parents[1] / "system" / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.broker_fee import build_fee_calibration_record, extract_actual_charges_total  # noqa: E402
from engine.broker_fee_artifacts import record_fee_calibration, summarize_fee_calibration  # noqa: E402


_TIGER_US_FEE_SCHEDULE = {
    "markets": {
        "US": {
            "stocks_etf": {
                "commission_per_share": 0.0049,
                "commission_min": 0.99,
                "platform_per_share": 0.005,
                "platform_min": 1.0,
                "platform_max_pct_trade_value": 0.005,
                "settlement_per_share": 0.003,
                "settlement_max_pct_trade_value": 0.07,
                "sec_sell_rate": 0.0000206,
                "sec_sell_min": 0.01,
                "taf_sell_per_share": 0.000195,
                "taf_sell_min": 0.01,
                "taf_sell_max": 9.79,
            }
        }
    }
}


class BrokerFeeCalibrationTests(unittest.TestCase):
    def test_extract_actual_charges_total_from_nested_charge_payload(self):
        payload = {
            "charges": {
                "commission": {"amount": 0.99},
                "platform_fee": {"amount": 1.0},
                "settlement_fee": {"amount": 0.03},
                "sec_fee": {"amount": 0.0206},
            }
        }
        self.assertAlmostEqual(extract_actual_charges_total(payload), 2.0406, places=6)

    def test_build_fee_calibration_record_compares_estimate_and_actual(self):
        record = build_fee_calibration_record(
            broker_platform="tiger",
            market="US",
            symbol="AAPL",
            side="SELL",
            price=100.0,
            quantity=10.0,
            actual_total=2.0506,
            fee_schedule=_TIGER_US_FEE_SCHEDULE,
        )
        self.assertIsNotNone(record)
        self.assertEqual(record["symbol"], "AAPL")
        self.assertAlmostEqual(record["estimated_total"], 2.0506, places=6)
        self.assertAlmostEqual(record["delta"], 0.0, places=6)

    def test_record_fee_calibration_writes_canonical_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                path = record_fee_calibration(
                    {
                        "broker_platform": "tiger",
                        "symbol": "AAPL",
                        "actual_total": 2.01,
                        "estimated_total": 2.05,
                        "delta": -0.04,
                    }
                )
                record = json.loads(path.read_text().splitlines()[0])
                summary = json.loads((artifacts_dir / "broker" / "fee_calibration_summary.json").read_text())
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

        self.assertEqual(path, artifacts_dir / "broker" / "fee_calibration.jsonl")
        self.assertEqual(record["symbol"], "AAPL")
        self.assertAlmostEqual(record["delta"], -0.04, places=6)
        self.assertEqual(summary["count"], 1)
        self.assertAlmostEqual(summary["avg_delta"], -0.04, places=6)

    def test_summarize_fee_calibration_limits_recent_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                for idx in range(3):
                    record_fee_calibration(
                        {
                            "broker_platform": "tiger",
                            "symbol": f"SYM{idx}",
                            "actual_total": 2.0 + idx,
                            "estimated_total": 2.1 + idx,
                            "delta": -0.1,
                        }
                    )
                summary = summarize_fee_calibration(limit=2)
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["recent"][0]["symbol"], "SYM2")
        self.assertEqual(summary["recent"][1]["symbol"], "SYM1")


if __name__ == "__main__":
    unittest.main()
