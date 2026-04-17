import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "system" / "engine" / "src"))
sys.modules.setdefault("yfinance", SimpleNamespace(download=lambda *args, **kwargs: None))

from engine.backtest import BacktestConfig, OrderSimulator


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


class BacktestFeeModelTests(unittest.TestCase):
    def test_tiger_us_buy_fee_breakdown_uses_minimums(self):
        simulator = OrderSimulator(
            broker_platform="tiger",
            market="US",
            fee_model="broker_default",
            fee_schedule=_TIGER_US_FEE_SCHEDULE,
        )

        breakdown = simulator.calculate_fee_breakdown(100.0, 10, "BUY")

        self.assertEqual(
            breakdown,
            {
                "commission": 0.99,
                "platform_fee": 1.0,
                "settlement_fee": 0.03,
            },
        )
        self.assertEqual(simulator.calculate_commission(100.0, 10, "BUY"), 2.02)

    def test_tiger_us_sell_fee_breakdown_adds_regulatory_fees(self):
        simulator = OrderSimulator(
            broker_platform="tiger",
            market="US",
            fee_model="broker_default",
            fee_schedule=_TIGER_US_FEE_SCHEDULE,
        )

        breakdown = simulator.calculate_fee_breakdown(100.0, 10, "SELL")

        self.assertEqual(breakdown["commission"], 0.99)
        self.assertEqual(breakdown["platform_fee"], 1.0)
        self.assertEqual(breakdown["settlement_fee"], 0.03)
        self.assertEqual(breakdown["sec_fee"], 0.0206)
        self.assertEqual(breakdown["taf_fee"], 0.01)
        self.assertAlmostEqual(simulator.calculate_commission(100.0, 10, "SELL"), 2.0506, places=6)

    def test_backtest_config_defaults_to_broker_default_fee_model(self):
        config = BacktestConfig(symbols=["AAPL"], start_date="2026-01-01", end_date="2026-04-01")
        self.assertEqual(config.broker_platform, "tiger")
        self.assertEqual(config.market, "US")
        self.assertEqual(config.fee_model, "broker_default")


if __name__ == "__main__":
    unittest.main()
