import unittest
from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "static"
PAGES = [
    STATIC_DIR / "index.html",
    STATIC_DIR / "strategy.html",
    STATIC_DIR / "logs.html",
]


class DashboardStaticHeadTests(unittest.TestCase):
    def test_all_pages_use_shared_head_assets(self):
        for page in PAGES:
            html = page.read_text(encoding="utf-8")
            self.assertIn('<meta name="color-scheme" content="dark">', html)
            self.assertIn('<meta name="theme-color" content="#11111b">', html)
            self.assertIn('/static/dashboard-head.js', html)
            self.assertIn('/static/dashboard-base.css', html)

    def test_strategy_and_logs_pages_include_header_status_bar(self):
        for name in ("strategy.html", "logs.html"):
            html = (STATIC_DIR / name).read_text(encoding="utf-8")
            self.assertIn('/static/header-status.js', html)
            self.assertIn('id="market-status-us"', html)
            self.assertIn('id="market-session"', html)
            self.assertIn('id="et-time"', html)
            self.assertIn('id="trading-mode-badge"', html)
            self.assertIn('id="refresh-status"', html)
            self.assertIn('id="last-update"', html)

    def test_all_pages_use_unified_title_prefix(self):
        expected_titles = {
            "index.html": "<title>Agent Trading · 总览</title>",
            "strategy.html": "<title>Agent Trading · 策略</title>",
            "logs.html": "<title>Agent Trading · 日志</title>",
        }
        for page in PAGES:
            html = page.read_text(encoding="utf-8")
            self.assertIn(expected_titles[page.name], html)

    def test_index_header_uses_compact_market_and_update_labels(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('let usText = \'美股\';', html)
        self.assertIn("document.getElementById('last-update').textContent = '上次更新: ' + updateTime;", html)


if __name__ == "__main__":
    unittest.main()
