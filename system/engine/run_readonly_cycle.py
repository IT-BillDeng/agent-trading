from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engine.config import load_app_config, load_tiger_props
from engine.runtime import run_readonly_cycle
from engine.tiger_client import TigerClient as DefaultBrokerClient


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: python3 run_readonly_cycle.py <app_config.json> <broker_props.properties>')
        return 2

    app = load_app_config(sys.argv[1])
    props = load_tiger_props(sys.argv[2])
    client = DefaultBrokerClient(props)
    summary = run_readonly_cycle(client, app)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
