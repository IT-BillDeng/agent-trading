from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class DirectoryCleanupCompatibilityTests(unittest.TestCase):
    def test_legacy_strategy_import_still_resolves(self):
        strategy_module = importlib.import_module("engine.strategy")
        from engine.strategy import StrategyEngine, StrategySignal

        self.assertIs(StrategyEngine, strategy_module.StrategyEngine)
        self.assertIs(StrategySignal, strategy_module.StrategySignal)
        self.assertTrue(hasattr(strategy_module, "evaluate_symbol") or hasattr(StrategyEngine, "evaluate_symbol"))

    def test_new_strategy_skeleton_submodules_resolve(self):
        bindings = importlib.import_module("engine.strategy.bindings")
        evaluator = importlib.import_module("engine.strategy.evaluator")
        compatibility = importlib.import_module("engine.strategy.compatibility")
        strategy_module = importlib.import_module("engine.strategy")

        self.assertTrue(hasattr(bindings, "StrategyBinding"))
        self.assertTrue(hasattr(evaluator, "FactorFirstEvaluator"))
        self.assertIs(compatibility.LegacyStrategyEngine, strategy_module.StrategyEngine)

    def test_adapter_skeleton_reexports_legacy_types(self):
        broker = importlib.import_module("engine.adapters.broker")
        market_data = importlib.import_module("engine.adapters.market_data")

        from engine.broker_client import BrokerClient
        from engine.data_provider import create_data_provider

        self.assertIs(broker.BrokerClient, BrokerClient)
        self.assertIs(market_data.create_data_provider, create_data_provider)


if __name__ == "__main__":
    unittest.main()
