import unittest
from datetime import date
from unittest import mock

from dashboard.trading_day import fetch_us_equity_holidays, get_us_trading_day_status


CALENDAR_HTML = """
<table>
  <tr><td>January 1, 2026</td><td>New Years Day (Observed)</td><td>Closed</td></tr>
  <tr><td>November 27, 2026</td><td>Early Close* - U.S.</td><td>1:00 p.m.</td></tr>
</table>
"""


class TradingDayHelperTests(unittest.TestCase):
    def setUp(self):
        fetch_us_equity_holidays.cache_clear()

    def tearDown(self):
        fetch_us_equity_holidays.cache_clear()

    def test_closed_holiday_is_not_trading_day(self):
        with mock.patch("dashboard.trading_day._fetch_calendar_page", return_value=CALENDAR_HTML):
            status = get_us_trading_day_status(target_date=date(2026, 1, 1))

        self.assertFalse(status.is_trading_day)
        self.assertEqual(status.reason, "holiday")
        self.assertEqual(status.holiday_name, "New Years Day (Observed)")
        self.assertEqual(status.holiday_status, "Closed")

    def test_early_close_day_is_still_trading_day(self):
        with mock.patch("dashboard.trading_day._fetch_calendar_page", return_value=CALENDAR_HTML):
            status = get_us_trading_day_status(target_date=date(2026, 11, 27))

        self.assertTrue(status.is_trading_day)
        self.assertEqual(status.reason, "open_day")
        self.assertEqual(status.holiday_status, "1:00 p.m.")

    def test_weekend_short_circuits_without_online_fetch(self):
        with mock.patch("dashboard.trading_day._fetch_calendar_page") as fetch_mock:
            status = get_us_trading_day_status(target_date=date(2026, 4, 18))

        self.assertFalse(status.is_trading_day)
        self.assertEqual(status.reason, "weekend")
        fetch_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
