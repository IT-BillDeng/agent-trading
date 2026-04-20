import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.control import ControlPlane


class ControlPlaneSafetyTests(unittest.TestCase):
    def test_default_state_allows_trade_when_unlocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)

            ok, reason = control.can_trade("US", "AAPL")

            self.assertTrue(ok)
            self.assertIsNone(reason)

    def test_locked_control_blocks_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)
            control.lock("manual test lock", updated_by="test")

            ok, reason = control.can_trade("US", "AAPL")

            self.assertFalse(ok)
            self.assertEqual(reason, "manual_lock_active")

    def test_default_state_file_is_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)

            payload = json.loads(Path(control.path).read_text())

            self.assertIn("global", payload)
            self.assertEqual(payload["global"]["trade_mode"], "paper_live")


if __name__ == "__main__":
    unittest.main()
