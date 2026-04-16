"""Tiger Engine CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    # Parse args: [--provider tiger|yfinance] <mode> <app_config.json> [tiger_props.properties]
    args = sys.argv[1:]
    provider = "tiger"

    if args and args[0] == "--provider" and len(args) >= 3:
        provider = args[1]
        args = args[2:]

    if len(args) < 2:
        print("Usage: python -m engine [--provider tiger|yfinance] <mode> <app_config.json> [tiger_props.properties]")
        print("Modes: readonly | strategy | dry-run | execution")
        print("Providers: tiger (default, needs props file) | yfinance (no props needed)")
        return 2

    mode = args[0]
    config_path = args[1]
    props_path = args[2] if len(args) > 2 else None

    from .config import load_app_config, load_tiger_props
    from .data_provider import create_data_provider
    from .tiger_client import TigerClient

    app = load_app_config(config_path)

    # Create data provider
    if provider == "yfinance":
        data = create_data_provider("yfinance")
        # yfinance doesn't need the broker client, but we still create one for trade ops
        client = None
        if props_path:
            props = load_tiger_props(props_path)
            client = TigerClient(props)
    elif provider == "tiger":
        if not props_path:
            print("Error: tiger provider requires tiger_props.properties file")
            return 2
        props = load_tiger_props(props_path)
        client = TigerClient(props)
        data = create_data_provider("tiger", props=props)
    else:
        print(f"Unknown provider: {provider}")
        return 2

    # Run cycle
    from .runtime import run_cycle
    summary = run_cycle(mode, client, data, app)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
