from __future__ import annotations

import sys
from datetime import date, datetime

from fastapi.responses import JSONResponse
from pydantic import BaseModel


_dashboard_main_module = None


def set_dashboard_main_module(module) -> None:
    global _dashboard_main_module
    _dashboard_main_module = module


def _dashboard_main():
    if _dashboard_main_module is not None:
        return _dashboard_main_module
    module = sys.modules.get("dashboard.main")
    if module is not None:
        return module
    from dashboard import main as dashboard_main
    return dashboard_main


class WatchlistItem(BaseModel):
    symbol: str
    market: str = "US"
    name: str = ""
    enabled: bool = True
    priority: str = "normal"
    notes: str = ""


class WatchlistUpdate(BaseModel):
    enabled: bool | None = None
    priority: str | None = None
    notes: str | None = None


async def api_account():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main._current_normalizer().account(dashboard_main.cache.get_account())


async def api_positions():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main._current_normalizer().positions(dashboard_main.cache.get_positions())


async def api_quotes():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main.cache.get_quotes()


async def api_orders():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main._current_normalizer().orders(dashboard_main.cache.get_orders())


async def api_pnl():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main._current_normalizer().pnl(dashboard_main.cache.get_pnl())


async def api_stock_analysis(period: str = "all"):
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main.cache.get_stock_analysis(period=period)


async def api_trading_day(date_str: str | None = None, market: str = "US"):
    dashboard_main = _dashboard_main()

    normalized_market = market.upper()
    if normalized_market != "US":
        return JSONResponse({"error": "unsupported market"}, status_code=400)

    try:
        target_date = date.fromisoformat(date_str) if date_str else None
    except ValueError:
        return JSONResponse({"error": "invalid date, expected YYYY-MM-DD"}, status_code=400)

    try:
        status = dashboard_main.get_us_trading_day_status(target_date=target_date)
    except Exception as e:
        dashboard_main.append_service_log(
            "dashboard",
            "warning",
            "Trading day lookup failed",
            kind="online_lookup_warning",
            market=normalized_market,
            date=date_str,
            error=str(e),
        )
        return JSONResponse(
            {
                "market": normalized_market,
                "date": target_date.isoformat() if target_date else None,
                "error": "online lookup failed",
                "detail": str(e),
            },
            status_code=503,
        )

    return status.__dict__


async def api_lookup_symbol(symbol: str):
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol.upper())
        info = ticker.info or {}
        name = info.get("shortName") or info.get("longName") or symbol.upper()
        return {"symbol": symbol.upper(), "name": name}
    except Exception:
        return {"symbol": symbol.upper(), "name": symbol.upper()}


async def api_market_status():
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)
    is_weekday = now_et.weekday() < 5
    is_trading_day = is_weekday
    hour = now_et.hour
    minute = now_et.minute
    t = hour * 60 + minute

    if not is_trading_day:
        session = "closed"
        session_label = "休市"
    elif 240 <= t < 570:
        session = "premarket"
        session_label = "盘前"
    elif 570 <= t < 960:
        session = "regular"
        session_label = "开盘中"
    elif 960 <= t < 1200:
        session = "afterhours"
        session_label = "盘后"
    else:
        session = "closed"
        session_label = "闭市"

    today_et = now_et.strftime("%Y-%m-%d")
    return {
        "is_trading_day": is_trading_day,
        "session": session,
        "session_label": session_label,
        "date_et": today_et,
        "now_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": str(now_et.tzinfo),
        "is_dst": bool(now_et.dst() and now_et.dst().total_seconds() > 0),
    }


async def api_watchlist():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main.cache.get_watchlist()


async def api_agents():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main.cache.get_agents()


async def api_system():
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return dashboard_main.cache.get_system()


async def api_watchlist_add(item: WatchlistItem):
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        result = dashboard_main.cache.add_symbol(item.model_dump())
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_watchlist_update(symbol: str, update: WatchlistUpdate):
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        result = dashboard_main.cache.update_symbol(symbol, update.model_dump(exclude_unset=True))
        if result is None:
            return JSONResponse({"error": f"Symbol {symbol} not found"}, status_code=404)
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_watchlist_remove(symbol: str):
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        result = dashboard_main.cache.remove_symbol(symbol)
        if not result:
            return JSONResponse({"error": f"Symbol {symbol} not found"}, status_code=404)
        return {"status": "ok", "removed": symbol}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


class RefreshConfig(BaseModel):
    interval: int | None = None


async def api_refresh(config: RefreshConfig):
    dashboard_main = _dashboard_main()

    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    if config.interval is not None:
        if config.interval < 5:
            return JSONResponse({"error": "minimum interval is 5 seconds"}, status_code=400)
        dashboard_main.cache._interval = config.interval
    return {"status": "ok", "interval": dashboard_main.cache._interval}


async def api_broker():
    dashboard_main = _dashboard_main()

    return {
        "current": dashboard_main._current_broker_platform(),
        "available": dashboard_main.available_brokers(),
    }


async def api_quote_providers():
    dashboard_main = _dashboard_main()

    return {
        "providers": [
            {"id": "yfinance", "name": "Yahoo Finance", "desc": "免费,有延迟"},
            {"id": "tiger", "name": "Broker API", "desc": "需要行情权限"},
        ],
        "current": dashboard_main.cache._quote_provider.name if dashboard_main.cache else None,
    }


async def api_quote_provider(body: dict):
    dashboard_main = _dashboard_main()

    provider = body.get("provider")
    if provider not in ("yfinance", "tiger"):
        return JSONResponse({"error": "invalid provider"}, status_code=400)
    if not dashboard_main.cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        new_provider = dashboard_main.get_quote_provider(provider, config_dir=str(dashboard_main.CONFIG_DIR_PATH))
        dashboard_main.cache._quote_provider = new_provider
        return {"status": "ok", "provider": provider, "name": new_provider.name}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def register_market_routes(app) -> None:
    app.get("/api/account")(api_account)
    app.get("/api/positions")(api_positions)
    app.get("/api/quotes")(api_quotes)
    app.get("/api/orders")(api_orders)
    app.get("/api/pnl")(api_pnl)
    app.get("/api/stock-analysis")(api_stock_analysis)
    app.get("/api/trading-day")(api_trading_day)
    app.get("/api/lookup/{symbol}")(api_lookup_symbol)
    app.get("/api/market-status")(api_market_status)
    app.get("/api/watchlist")(api_watchlist)
    app.get("/api/agents")(api_agents)
    app.get("/api/system")(api_system)
    app.post("/api/watchlist")(api_watchlist_add)
    app.patch("/api/watchlist/{symbol}")(api_watchlist_update)
    app.delete("/api/watchlist/{symbol}")(api_watchlist_remove)
    app.post("/api/refresh")(api_refresh)
    app.get("/api/broker")(api_broker)
    app.get("/api/quote-providers")(api_quote_providers)
    app.post("/api/quote-provider")(api_quote_provider)
