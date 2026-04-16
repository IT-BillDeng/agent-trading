import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "system" / "engine" / "src"))

from engine.config import load_app_config_raw


class ConfigBrokerPlatformTests(unittest.TestCase):
    def test_broker_platform_merges_from_user_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            defaults = root / "app.defaults.json"
            overlay = root / "app_config.docker.json"
            user_settings = root / "user.settings.json"

            defaults.write_text(json.dumps({
                "mode": "paper",
                "broker": {"platform": "tiger"},
                "strategy": {"timeframe": "30min"},
            }, ensure_ascii=False))
            overlay.write_text(json.dumps({
                "extends": "./app.defaults.json",
                "strategy": {"watchlist_file": "/app/data/watchlist.json"},
            }, ensure_ascii=False))
            user_settings.write_text(json.dumps({
                "broker": {"platform": "mock-broker"},
            }, ensure_ascii=False))

            config = load_app_config_raw(overlay)

            self.assertEqual(config["broker"]["platform"], "mock-broker")
            self.assertEqual(config["strategy"]["timeframe"], "30min")


if __name__ == "__main__":
    unittest.main()
