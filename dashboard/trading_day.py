"""Online U.S. trading-day helpers backed by Nasdaq Trader holiday calendar."""

from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo


NASDAQ_TRADER_CALENDAR_URL = "https://www.nasdaqtrader.com/Trader.aspx?id=calendar"
ET_ZONE = ZoneInfo("America/New_York")

HOLIDAY_ROW_RE = re.compile(
    r"<tr><td>([A-Za-z]+\s+\d{1,2},\s+\d{4})</td><td>(.*?)</td><td>(.*?)</td></tr>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class TradingDayStatus:
    market: str
    date: str
    timezone: str
    is_trading_day: bool
    reason: str
    source: str
    checked_at: str
    holiday_name: str | None = None
    holiday_status: str | None = None


def _fetch_calendar_page() -> str:
    req = urllib.request.Request(
        NASDAQ_TRADER_CALENDAR_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "ignore")


@lru_cache(maxsize=4)
def fetch_us_equity_holidays(year: int) -> dict[date, dict[str, str]]:
    text = html.unescape(_fetch_calendar_page())
    rows = HOLIDAY_ROW_RE.findall(text)
    holidays: dict[date, dict[str, str]] = {}
    for raw_day, raw_name, raw_status in rows:
        parsed_day = datetime.strptime(raw_day, "%B %d, %Y").date()
        if parsed_day.year != year:
            continue
        holidays[parsed_day] = {
            "name": re.sub(r"\s+", " ", raw_name).strip(),
            "status": re.sub(r"\s+", " ", raw_status).strip(),
        }
    return holidays


def get_us_trading_day_status(target_date: date | None = None) -> TradingDayStatus:
    now_et = datetime.now(ET_ZONE)
    trading_date = target_date or now_et.date()

    if trading_date.weekday() >= 5:
        return TradingDayStatus(
            market="US",
            date=trading_date.isoformat(),
            timezone="America/New_York",
            is_trading_day=False,
            reason="weekend",
            source=NASDAQ_TRADER_CALENDAR_URL,
            checked_at=now_et.isoformat(),
        )

    holidays = fetch_us_equity_holidays(trading_date.year)
    holiday = holidays.get(trading_date)
    if holiday and holiday["status"].lower() == "closed":
        return TradingDayStatus(
            market="US",
            date=trading_date.isoformat(),
            timezone="America/New_York",
            is_trading_day=False,
            reason="holiday",
            source=NASDAQ_TRADER_CALENDAR_URL,
            checked_at=now_et.isoformat(),
            holiday_name=holiday["name"],
            holiday_status=holiday["status"],
        )

    return TradingDayStatus(
        market="US",
        date=trading_date.isoformat(),
        timezone="America/New_York",
        is_trading_day=True,
        reason="open_day",
        source=NASDAQ_TRADER_CALENDAR_URL,
        checked_at=now_et.isoformat(),
        holiday_name=holiday["name"] if holiday else None,
        holiday_status=holiday["status"] if holiday else None,
    )
