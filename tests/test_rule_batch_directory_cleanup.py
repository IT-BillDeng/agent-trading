from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RuleBatchDirectoryCleanupTests(unittest.TestCase):
    def test_rule_batches_live_under_experiments_directory(self):
        batches_dir = ROOT / "experiments" / "rule_batches"
        rules_dir = ROOT / "rules"
        expected = {
            "_batch_baseline.json",
            "_batch_baseline_current.json",
            "_batch_bb_vol_1_1.json",
            "_batch_disable_rsi.json",
            "_batch_rsi25_bb14_trend_on.json",
            "_batch_rsi_oversold_20.json",
            "_batch_rsi_oversold_35.json",
            "_batch_trend_follow_guarded.json",
            "_batch_trend_guarded.json",
        }

        self.assertTrue(batches_dir.exists())
        self.assertTrue(expected.issubset({path.name for path in batches_dir.glob("_batch_*.json")}))
        self.assertEqual(list(rules_dir.glob("_batch_*.json")), [])


if __name__ == "__main__":
    unittest.main()
