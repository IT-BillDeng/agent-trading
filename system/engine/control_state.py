from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engine.control import ControlPlane
from engine.config import load_app_config


def main() -> int:
    if len(sys.argv) < 3:
        print('usage: python3 control_state.py <app_config.json> <status|lock|unlock> [reason]')
        return 2

    app = load_app_config(sys.argv[1])
    action = sys.argv[2]
    reason = sys.argv[3] if len(sys.argv) >= 4 else ('manual_lock' if action == 'lock' else 'manual_unlock')
    state_dir = app.raw.get('system', {}).get('state_dir', './state')
    if not Path(state_dir).is_absolute():
        state_dir = ROOT / state_dir
    control = ControlPlane(state_dir)

    if action == 'status':
        result = control.status()
    elif action == 'lock':
        result = control.lock(reason, updated_by='operator')
    elif action == 'unlock':
        result = control.unlock(reason, updated_by='operator')
    else:
        print(f'unknown action: {action}')
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
