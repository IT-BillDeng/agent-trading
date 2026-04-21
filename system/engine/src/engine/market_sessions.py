from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


ET_ZONE = ZoneInfo("America/New_York")


def market_data_policy(app_config: dict[str, Any]) -> dict[str, Any]:
    strategy = dict(app_config.get("strategy", {}))
    policy = dict(strategy.get("market_data", {}))
    return {
        "include_extended_hours": bool(policy.get("include_extended_hours", True)),
        "extended_hours_usage": str(policy.get("extended_hours_usage", "context_only")),
        "regular_session_only_for_indicators": bool(policy.get("regular_session_only_for_indicators", True)),
        "require_completed_bar_for_actionable_signal": bool(
            policy.get("require_completed_bar_for_actionable_signal", True)
        ),
    }


def session_config(app_config: dict[str, Any], market: str) -> dict[str, Any]:
    strategy = dict(app_config.get("strategy", {}))
    sessions = dict(strategy.get("sessions", {}))
    market_cfg = dict(sessions.get(market, {}))
    timezone_name = str(market_cfg.get("timezone") or "America/New_York")
    return {
        "regular_start": str(market_cfg.get("regular_start") or "09:30"),
        "regular_end": str(market_cfg.get("regular_end") or "16:00"),
        "entry_window_start": str(market_cfg.get("entry_window_start") or "10:00"),
        "entry_window_end": str(market_cfg.get("entry_window_end") or "15:15"),
        "timezone": timezone_name,
    }


def parse_timestamp(value: Any, *, assume_tz: ZoneInfo | None = None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=assume_tz or timezone.utc)
    text = str(value)
    if text.isdigit():
        ts = float(text)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=assume_tz or timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=assume_tz or ET_ZONE)
    return parsed


def parse_bar_timestamp(bar: dict[str, Any], *, timezone_name: str = "America/New_York") -> datetime | None:
    tz = ZoneInfo(timezone_name)
    for key in ("time", "timestamp", "date", "datetime"):
        value = bar.get(key)
        parsed = parse_timestamp(value, assume_tz=tz)
        if parsed is not None:
            return parsed.astimezone(tz)
    return None


def resolve_timestamp(asset_snapshot: dict[str, Any] | None) -> str | None:
    snapshot = asset_snapshot or {}
    for key in (
        "trading_timestamp",
        "tradingTimestamp",
        "account_timestamp",
        "accountTimestamp",
        "broker_timestamp",
        "brokerTimestamp",
        "timestamp",
        "ts",
        "updated_at",
        "as_of",
    ):
        value = snapshot.get(key)
        if value:
            return str(value)
    return None


def resolve_now_for_market(
    asset_snapshot: dict[str, Any] | None,
    bars: list[dict[str, Any]] | None,
    *,
    timezone_name: str = "America/New_York",
) -> datetime:
    tz = ZoneInfo(timezone_name)
    parsed = parse_timestamp(resolve_timestamp(asset_snapshot), assume_tz=timezone.utc)
    if parsed is not None:
        return parsed.astimezone(tz)
    bars = list(bars or [])
    if bars:
        bar_dt = parse_bar_timestamp(bars[-1], timezone_name=timezone_name)
        if bar_dt is not None:
            return bar_dt
    return datetime.now(tz)


def resolve_trading_day_for_market(
    asset_snapshot: dict[str, Any] | None,
    bars: list[dict[str, Any]] | None,
    *,
    timezone_name: str = "America/New_York",
) -> str:
    snapshot = asset_snapshot or {}
    for key in ("trading_day", "tradingDay", "date"):
        value = snapshot.get(key)
        if value:
            return str(value)[:10]
    return resolve_now_for_market(asset_snapshot, bars, timezone_name=timezone_name).date().isoformat()


def _parse_hhmm(value: str, default_value: str) -> time:
    text = str(value or default_value)
    try:
        hour_text, minute_text = text.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except Exception:
        return _parse_hhmm(default_value, default_value)


def classify_bar_session(bar_dt: datetime, *, market: str, session_cfg: dict[str, Any]) -> str:
    if market != "US":
        return "regular"
    local_dt = bar_dt.astimezone(ZoneInfo(session_cfg["timezone"]))
    local_time = local_dt.timetz().replace(tzinfo=None)
    regular_start = _parse_hhmm(session_cfg["regular_start"], "09:30")
    regular_end = _parse_hhmm(session_cfg["regular_end"], "16:00")
    premarket_start = time(4, 0)
    afterhours_end = time(20, 0)
    if regular_start <= local_time < regular_end:
        return "regular"
    if premarket_start <= local_time < regular_start:
        return "premarket"
    if regular_end <= local_time < afterhours_end:
        return "afterhours"
    return "offhours"


def timeframe_delta(timeframe: str) -> timedelta | None:
    value = str(timeframe or "").strip().lower()
    mapping = {
        "1min": timedelta(minutes=1),
        "5min": timedelta(minutes=5),
        "15min": timedelta(minutes=15),
        "30min": timedelta(minutes=30),
        "60min": timedelta(minutes=60),
        "1hour": timedelta(hours=1),
    }
    return mapping.get(value)


def is_bar_complete(
    bar_dt: datetime,
    *,
    timeframe: str,
    now_dt: datetime,
) -> bool:
    delta = timeframe_delta(timeframe)
    if delta is None:
        return True
    if bar_dt.date() < now_dt.date():
        return True
    return bar_dt + delta <= now_dt


def _bar_close(bar: dict[str, Any]) -> float | None:
    value = bar.get("close")
    try:
        return float(value)
    except Exception:
        return None


def _bar_open(bar: dict[str, Any]) -> float | None:
    value = bar.get("open")
    try:
        return float(value)
    except Exception:
        return None


def _bar_high(bar: dict[str, Any]) -> float | None:
    value = bar.get("high")
    try:
        return float(value)
    except Exception:
        return None


def _bar_low(bar: dict[str, Any]) -> float | None:
    value = bar.get("low")
    try:
        return float(value)
    except Exception:
        return None


def _bar_volume(bar: dict[str, Any]) -> float:
    value = bar.get("volume")
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _pct_change(current: float | None, base: float | None) -> float | None:
    if current is None or base in (None, 0):
        return None
    return (current - base) / base


def analyze_symbol_bars(
    bars: list[dict[str, Any]],
    *,
    asset_snapshot: dict[str, Any] | None,
    market: str,
    timeframe: str,
    app_config: dict[str, Any],
    provider: str | None = None,
) -> dict[str, Any]:
    policy = market_data_policy(app_config)
    session_cfg = session_config(app_config, market)
    timezone_name = session_cfg["timezone"]
    now_dt = resolve_now_for_market(asset_snapshot, bars, timezone_name=timezone_name)
    trading_day = resolve_trading_day_for_market(asset_snapshot, bars, timezone_name=timezone_name)
    current_day = trading_day

    parsed_rows: list[dict[str, Any]] = []
    for bar in bars:
        bar_dt = parse_bar_timestamp(bar, timezone_name=timezone_name)
        if bar_dt is None:
            continue
        session = classify_bar_session(bar_dt, market=market, session_cfg=session_cfg)
        parsed_rows.append(
            {
                "bar": dict(bar),
                "dt": bar_dt,
                "session": session,
                "is_complete": is_bar_complete(bar_dt, timeframe=timeframe, now_dt=now_dt),
            }
        )

    parsed_rows.sort(key=lambda item: item["dt"])
    raw_bars = [item["bar"] for item in parsed_rows]
    regular_rows = [item for item in parsed_rows if item["session"] == "regular"]
    regular_completed_rows = [item for item in regular_rows if item["is_complete"]]
    extended_rows = [item for item in parsed_rows if item["session"] in {"premarket", "afterhours"}]
    premarket_rows = [item for item in parsed_rows if item["session"] == "premarket"]
    afterhours_rows = [item for item in parsed_rows if item["session"] == "afterhours"]

    latest_raw_row = parsed_rows[-1] if parsed_rows else None
    latest_regular_row = regular_rows[-1] if regular_rows else None
    latest_completed_regular_row = regular_completed_rows[-1] if regular_completed_rows else None
    first_regular_same_day_row = next(
        (
            item
            for item in regular_rows
            if item["dt"].date().isoformat() == current_day
            and item["dt"].time() == _parse_hhmm(session_cfg["regular_start"], "09:30")
        ),
        None,
    )

    first_regular_30m_bar_completed = bool(first_regular_same_day_row and first_regular_same_day_row["is_complete"])
    latest_regular_is_complete = bool(latest_regular_row and latest_regular_row["is_complete"])
    latest_regular_is_stale = bool(
        latest_completed_regular_row
        and latest_completed_regular_row["dt"].date().isoformat() != current_day
        and now_dt.time() >= _parse_hhmm(session_cfg["regular_start"], "09:30")
    )

    entry_start = _parse_hhmm(session_cfg["entry_window_start"], "10:00")
    entry_end = _parse_hhmm(session_cfg["entry_window_end"], "15:15")
    regular_start = _parse_hhmm(session_cfg["regular_start"], "09:30")
    first_bar_delta = timeframe_delta(timeframe) or timedelta(minutes=30)

    actionable_block_reason = None
    if market == "US" and timeframe == "30min" and policy["regular_session_only_for_indicators"]:
        if now_dt.time() >= entry_end:
            actionable_block_reason = "entry_window_closed"
        elif regular_start <= now_dt.time() < (datetime.combine(now_dt.date(), regular_start, tzinfo=now_dt.tzinfo) + first_bar_delta).time():
            actionable_block_reason = "first_30m_bar_not_closed"
        elif now_dt.time() < entry_start:
            actionable_block_reason = "entry_window_not_open"
        elif not first_regular_30m_bar_completed:
            actionable_block_reason = (
                "latest_regular_bar_stale" if latest_regular_is_stale else "first_regular_bar_missing"
            )

    if actionable_block_reason is None and policy["extended_hours_usage"] == "context_only" and extended_rows and not regular_rows:
        actionable_block_reason = "extended_context_only"

    previous_regular_close = _bar_close(latest_completed_regular_row["bar"]) if latest_completed_regular_row else None
    first_current_day_regular_open = _bar_open(first_regular_same_day_row["bar"]) if first_regular_same_day_row else None
    premarket_closes = [_bar_close(item["bar"]) for item in premarket_rows if _bar_close(item["bar"]) is not None]
    afterhours_closes = [_bar_close(item["bar"]) for item in afterhours_rows if _bar_close(item["bar"]) is not None]
    premarket_highs = [_bar_high(item["bar"]) for item in premarket_rows if _bar_high(item["bar"]) is not None]
    premarket_lows = [_bar_low(item["bar"]) for item in premarket_rows if _bar_low(item["bar"]) is not None]
    latest_regular_close = _bar_close(latest_regular_row["bar"]) if latest_regular_row else None

    premarket_gap_pct = _pct_change(premarket_closes[-1] if premarket_closes else None, previous_regular_close)
    premarket_range_pct = (
        ((max(premarket_highs) - min(premarket_lows)) / previous_regular_close)
        if premarket_highs and premarket_lows and previous_regular_close not in (None, 0)
        else None
    )
    afterhours_move_pct = _pct_change(afterhours_closes[-1] if afterhours_closes else None, latest_regular_close)
    overnight_return_pct = _pct_change(
        first_current_day_regular_open or (premarket_closes[-1] if premarket_closes else None),
        previous_regular_close,
    )

    return {
        "now_et": now_dt,
        "trading_day": current_day,
        "raw_bars": raw_bars,
        "regular_bars": [item["bar"] for item in regular_rows],
        "regular_completed_bars": [item["bar"] for item in regular_completed_rows],
        "extended_bars": [item["bar"] for item in extended_rows],
        "premarket_bars": [item["bar"] for item in premarket_rows],
        "afterhours_bars": [item["bar"] for item in afterhours_rows],
        "raw_bars_count": len(parsed_rows),
        "regular_bars_count": len(regular_rows),
        "regular_completed_bars_count": len(regular_completed_rows),
        "extended_bars_count": len(extended_rows),
        "latest_raw_bar_time": latest_raw_row["dt"].isoformat() if latest_raw_row else None,
        "latest_regular_bar_time": latest_regular_row["dt"].isoformat() if latest_regular_row else None,
        "latest_regular_bar_is_complete": latest_regular_is_complete,
        "latest_regular_bar_is_stale": latest_regular_is_stale,
        "first_regular_30m_bar_completed": first_regular_30m_bar_completed,
        "actionable_ready": actionable_block_reason is None,
        "actionable_block_reason": actionable_block_reason,
        "extended_context": {
            "has_extended_data": bool(extended_rows),
            "premarket_bars_count": len(premarket_rows),
            "afterhours_bars_count": len(afterhours_rows),
            "premarket_gap_pct": premarket_gap_pct,
            "premarket_volume": sum(_bar_volume(item["bar"]) for item in premarket_rows),
            "premarket_range_pct": premarket_range_pct,
            "afterhours_move_pct": afterhours_move_pct,
            "overnight_return_pct": overnight_return_pct,
            "provider": provider,
        },
    }
