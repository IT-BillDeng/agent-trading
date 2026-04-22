from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.store import FactorStore


class FactorStoreTests(unittest.TestCase):
    def test_write_snapshot_writes_latest_and_history_under_temp_artifacts_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_dir = root / "artifacts" / "factors"
            store = FactorStore(artifacts_dir=artifacts_dir)
            snapshot = {
                "timestamp": "2026-04-20T14:30:00+00:00",
                "registry_hash": "registry-hash",
                "mode": "shadow",
                "symbols": {
                    "AAPL": {
                        "factors": {
                            "rsi_14_30m": {
                                "value": 42.0,
                                "ready": True,
                                "actionable": False,
                                "source": "regular_session_completed_bars",
                                "reason": "ok",
                                "config_hash": "hash-rsi",
                            }
                        }
                    }
                },
            }

            paths = store.write_snapshot(snapshot)

            latest = artifacts_dir / "latest.json"
            history = artifacts_dir / "history" / "2026-04-20.jsonl"
            self.assertEqual(paths["latest"], latest)
            self.assertEqual(paths["history"], history)
            self.assertTrue(latest.exists())
            self.assertTrue(history.exists())
            self.assertTrue(str(latest).startswith(str(root)))
            self.assertEqual(json.loads(latest.read_text())["registry_hash"], "registry-hash")
            self.assertGreaterEqual(len(history.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
