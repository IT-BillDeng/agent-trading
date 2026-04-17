from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_fee_schedule(broker_platform: str) -> dict[str, Any]:
    config_dir = Path(
        os.environ.get(
            "ENGINE_CONFIG_DIR",
            str(Path(__file__).resolve().parents[4] / "config"),
        )
    )
    schedule_file = config_dir / f"broker_fee.{broker_platform}.json"
    if not schedule_file.exists():
        return {}
    try:
        payload = json.loads(schedule_file.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def estimate_order_fee_breakdown(
    *,
    broker_platform: str,
    market: str,
    side: str,
    price: float,
    quantity: float,
    fee_schedule: dict[str, Any] | None = None,
) -> dict[str, float]:
    schedule = fee_schedule or load_fee_schedule(broker_platform)
    if broker_platform == "tiger" and market == "US":
        return _estimate_tiger_us_stock_fee_breakdown(schedule, side, price, quantity)
    return {}


def estimate_order_fee_total(
    *,
    broker_platform: str,
    market: str,
    side: str,
    price: float,
    quantity: float,
    fee_schedule: dict[str, Any] | None = None,
) -> float:
    breakdown = estimate_order_fee_breakdown(
        broker_platform=broker_platform,
        market=market,
        side=side,
        price=price,
        quantity=quantity,
        fee_schedule=fee_schedule,
    )
    return round(sum(breakdown.values()), 6) if breakdown else 0.0


def extract_actual_charges_total(order_item: dict[str, Any] | None) -> float | None:
    if not isinstance(order_item, dict):
        return None

    charges = order_item.get("charges")
    if charges is None:
        return None

    total = _extract_charge_value(charges)
    return round(total, 6) if total is not None else None


def build_fee_calibration_record(
    *,
    broker_platform: str,
    market: str,
    symbol: str | None,
    side: str | None,
    price: float | None,
    quantity: float | None,
    actual_total: float | None,
    fee_schedule: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if side is None or price is None or quantity is None or quantity <= 0 or actual_total is None:
        return None

    estimated_breakdown = estimate_order_fee_breakdown(
        broker_platform=broker_platform,
        market=market,
        side=side,
        price=price,
        quantity=quantity,
        fee_schedule=fee_schedule,
    )
    estimated_total = round(sum(estimated_breakdown.values()), 6)

    return {
        "broker_platform": broker_platform,
        "market": market,
        "symbol": symbol,
        "side": side,
        "price": round(float(price), 6),
        "quantity": round(float(quantity), 6),
        "estimated_total": estimated_total,
        "estimated_breakdown": estimated_breakdown,
        "actual_total": round(actual_total, 6),
        "delta": round(actual_total - estimated_total, 6),
    }


def _estimate_tiger_us_stock_fee_breakdown(
    schedule: dict[str, Any],
    side: str,
    price: float,
    quantity: float,
) -> dict[str, float]:
    product = (
        schedule.get("markets", {})
        .get("US", {})
        .get("stocks_etf", {})
    )
    if not product:
        return {}

    trade_value = float(price) * float(quantity)
    breakdown: dict[str, float] = {}

    commission = max(float(quantity) * float(product.get("commission_per_share", 0.0)), float(product.get("commission_min", 0.0)))
    breakdown["commission"] = round(commission, 6)

    platform_fee = max(float(quantity) * float(product.get("platform_per_share", 0.0)), float(product.get("platform_min", 0.0)))
    platform_cap = trade_value * float(product.get("platform_max_pct_trade_value", 0.0))
    if platform_cap > 0:
        platform_fee = min(platform_fee, platform_cap)
    breakdown["platform_fee"] = round(platform_fee, 6)

    settlement_fee = float(quantity) * float(product.get("settlement_per_share", 0.0))
    settlement_cap = trade_value * float(product.get("settlement_max_pct_trade_value", 0.0))
    if settlement_cap > 0:
        settlement_fee = min(settlement_fee, settlement_cap)
    breakdown["settlement_fee"] = round(settlement_fee, 6)

    if str(side).upper() == "SELL":
        sec_fee = max(trade_value * float(product.get("sec_sell_rate", 0.0)), float(product.get("sec_sell_min", 0.0)))
        breakdown["sec_fee"] = round(sec_fee, 6)

        taf_fee = float(quantity) * float(product.get("taf_sell_per_share", 0.0))
        taf_fee = max(taf_fee, float(product.get("taf_sell_min", 0.0)))
        taf_cap = float(product.get("taf_sell_max", 0.0))
        if taf_cap > 0:
            taf_fee = min(taf_fee, taf_cap)
        breakdown["taf_fee"] = round(taf_fee, 6)

    return breakdown


def _extract_charge_value(payload: Any) -> float | None:
    if isinstance(payload, (int, float)):
        return float(payload)

    if isinstance(payload, list):
        values = [_extract_charge_value(item) for item in payload]
        filtered = [value for value in values if value is not None]
        return sum(filtered) if filtered else None

    if isinstance(payload, dict):
        for key in ("total", "totalCharge", "total_charge", "amount", "value"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        total = 0.0
        matched = False
        for key, value in payload.items():
            if any(token in str(key).lower() for token in ("fee", "commission", "tax", "taf", "sec", "settlement", "platform", "gst", "stamp")):
                nested = _extract_charge_value(value)
                if nested is not None:
                    total += nested
                    matched = True
        return total if matched else None

    return None
