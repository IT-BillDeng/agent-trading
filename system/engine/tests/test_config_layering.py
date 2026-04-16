import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.config import load_app_config_raw, merge_user_settings, resolve_user_settings_path


class ConfigLayeringTests(unittest.TestCase):
    def test_load_app_config_raw_merges_defaults_overlay_and_user_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)

            (config_dir / "app.defaults.json").write_text(json.dumps({
                "mode": "paper",
                "markets": ["US"],
                "strategy": {"timeframe": "30min", "watchlist_file": "/defaults/watchlist.json"},
                "risk": {"daily_loss_limit_pct": 5},
                "notify": {"telegram_send_enabled": False},
            }, ensure_ascii=False))
            (config_dir / "app_config.docker.json").write_text(json.dumps({
                "extends": "./app.defaults.json",
                "strategy": {"watchlist_file": "/app/data/watchlist.json"},
                "system": {"state_dir": "/app/runtime/state"},
            }, ensure_ascii=False))
            (config_dir / "user.settings.json").write_text(json.dumps({
                "mode": "live",
                "markets": ["US", "HK"],
                "notify": {"telegram_send_enabled": True},
            }, ensure_ascii=False))

            merged = load_app_config_raw(config_dir / "app_config.docker.json")

            self.assertEqual(merged["mode"], "live")
            self.assertEqual(merged["markets"], ["US", "HK"])
            self.assertEqual(merged["strategy"]["timeframe"], "30min")
            self.assertEqual(merged["strategy"]["watchlist_file"], "/app/data/watchlist.json")
            self.assertEqual(merged["risk"]["daily_loss_limit_pct"], 5)
            self.assertTrue(merged["notify"]["telegram_send_enabled"])
            self.assertEqual(merged["system"]["state_dir"], "/app/runtime/state")

    def test_merge_user_settings_creates_local_settings_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)

            config_file = config_dir / "app_config.docker.json"
            config_file.write_text(json.dumps({"mode": "paper"}, ensure_ascii=False))

            merged, settings_path = merge_user_settings(config_file, {"markets": ["US"], "mode": "paper"})

            self.assertEqual(settings_path, resolve_user_settings_path(config_file))
            self.assertTrue(settings_path.exists())
            self.assertEqual(merged["markets"], ["US"])
            self.assertEqual(json.loads(settings_path.read_text())["mode"], "paper")


if __name__ == "__main__":
    unittest.main()
