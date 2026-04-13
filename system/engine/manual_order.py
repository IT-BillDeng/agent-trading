#!/usr/bin/env python3
"""Manual order placement for debugging.
Usage: python3 manual_order.py <tiger_props> <symbol> <quantity> <sl_pct> <tp_pct>
"""
import json
import sys
from pathlib import Path

# Add engine source to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from engine.tiger_client import TigerClient
from engine.config import load_tiger_props


def main():
    if len(sys.argv) != 6:
        print("usage: python3 manual_order.py <tiger_props> <symbol> <quantity> <sl_pct> <tp_pct>")
        print("example: python3 manual_order.py properties/tiger.properties NVDA 100 5 5")
        return 1

    props_path = sys.argv[1]
    symbol = sys.argv[2].upper()
    quantity = int(sys.argv[3])
    sl_pct = float(sys.argv[4])
    tp_pct = float(sys.argv[5])

    props = load_tiger_props(props_path)
    client = TigerClient(props)

    # 1. Get quote (yfinance fallback)
    print(f"[1/4] Getting quote for {symbol}...")
    latest_price = None
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        latest_price = float(t.info.get('currentPrice') or t.info.get('regularMarketPrice') or 0)
    except Exception:
        pass

    if not latest_price or latest_price <= 0:
        try:
            bars_resp = client.get_bars([symbol], period="1d", limit=1)
            bars_data = bars_resp.get("body", {}).get("data", [])
            if isinstance(bars_data, str):
                bars_data = json.loads(bars_data)
            if isinstance(bars_data, list) and bars_data:
                items = bars_data[0].get("items", []) if isinstance(bars_data[0], dict) else []
                if items:
                    latest_price = float(items[-1].get("close", 0))
        except Exception:
            pass

    if not latest_price or latest_price <= 0:
        print(f"ERROR: Cannot get price for {symbol}")
        return 1

    limit_price = round(latest_price * 1.001, 2)
    stop_loss = round(latest_price * (1 - sl_pct / 100), 2)
    take_profit = round(latest_price * (1 + tp_pct / 100), 2)

    print(f"  Price: ${latest_price:.2f}")
    print(f"  Limit: ${limit_price:.2f}")
    print(f"  SL:    ${stop_loss:.2f} (-{sl_pct}%)")
    print(f"  TP:    ${take_profit:.2f} (+{tp_pct}%)")

    # 2. Get order number
    print(f"[2/4] Getting order number...")
    order_no_resp = client.create_order_no()
    order_no_body = order_no_resp.get("body", {})
    order_no_data = order_no_body.get("data")
    if isinstance(order_no_data, str):
        try:
            order_no_data = json.loads(order_no_data)
        except:
            pass
    if isinstance(order_no_data, dict):
        order_id = order_no_data.get("orderId") or order_no_data.get("order_id") or order_no_data.get("id")
    elif isinstance(order_no_data, int):
        order_id = order_no_data
    else:
        order_id = order_no_data

    if not order_id:
        print(f"ERROR: Failed to get order number: {order_no_resp}")
        return 1
    print(f"  Order ID: {order_id}")

    # 3. Preview
    payload = {
        "symbol": symbol,
        "currency": "USD",
        "sec_type": "STK",
        "order_type": "LMT",
        "action": "BUY",
        "total_quantity": quantity,
        "time_in_force": "DAY",
        "outside_rth": False,
        "limit_price": limit_price,
        "order_id": int(order_id),
    }

    print(f"[3/4] Previewing order...")
    preview_resp = client.preview_order(payload)
    preview_body = preview_resp.get("body", {})
    preview_data = preview_body.get("data", {})
    if isinstance(preview_data, str):
        preview_data = json.loads(preview_data)

    is_pass = preview_data.get("isPass", True) if isinstance(preview_data, dict) else True
    msg = preview_data.get("message", "") if isinstance(preview_data, dict) else ""

    if not is_pass:
        print(f"  BLOCKED: {msg}")
        print(f"  availableEE: {preview_data.get('availableEE', 'N/A')}")
        print(f"  excessLiquidity: {preview_data.get('excessLiquidity', 'N/A')}")
        return 1
    print(f"  Preview OK")

    # 4. Place order
    print(f"[4/4] Placing order...")
    place_resp = client.place_order(payload)
    place_body = place_resp.get("body", {})
    ok = place_body.get("code") == 0

    if ok:
        data = place_body.get("data", {})
        if isinstance(data, str):
            data = json.loads(data)
        global_id = data.get("id") if isinstance(data, dict) else None
        print(f"  SUCCESS! Global ID: {global_id}")
    else:
        print(f"  FAILED: {place_body.get('message', 'unknown error')}")

    print(f"\nSummary:")
    print(f"  {symbol} BUY {quantity} @ ${limit_price:.2f}")
    print(f"  SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}")
    print(f"  Notional: ${limit_price * quantity:,.2f}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
