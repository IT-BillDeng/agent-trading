import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dashboard import data_cache


class WatchlistBootstrapTests(unittest.TestCase):
    def test_seed_watchlist_from_example_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            data_dir.mkdir()
            example_path = data_dir / "watchlist.json.example"
            target_path = data_dir / "watchlist.json"
            example_path.write_text('{"symbols":[{"symbol":"AAPL"}]}')

            with mock.patch.object(data_cache, "WATCHLIST_PATH", target_path):
                data_cache._seed_watchlist_if_missing()

            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_text(), example_path.read_text())


if __name__ == "__main__":
    unittest.main()
