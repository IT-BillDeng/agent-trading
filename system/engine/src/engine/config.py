from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]

    @property
    def strategy(self) -> dict[str, Any]:
        return dict(self.raw.get('strategy', {}))

    @property
    def watchlist_file(self) -> str | None:
        raw = self.raw.get('strategy', {}).get('watchlist_file')
        return str(raw) if raw else None

    @property
    def markets(self) -> list[str]:
        return list(self.raw.get('markets', ['US']))

    @property
    def symbols(self) -> list[dict[str, Any]]:
        shared = self._load_shared_watchlist_symbols()
        if not shared:
            shared = list(self.raw.get('strategy', {}).get('symbols', []))
        # Filter by enabled markets
        enabled_markets = set(self.markets)
        return [s for s in shared if s.get('market') in enabled_markets]

    @property
    def timeframe(self) -> str:
        return str(self.raw.get('strategy', {}).get('timeframe', '30min'))

    @property
    def signal(self) -> dict[str, Any]:
        return dict(self.raw.get('strategy', {}).get('signal', {}))

    @property
    def risk(self) -> dict[str, Any]:
        return dict(self.raw.get('risk', {}))

    def _load_shared_watchlist_symbols(self) -> list[dict[str, Any]]:
        if not self.watchlist_file:
            return []
        path = Path(self.watchlist_file)
        if not path.exists():
            return []
        payload = json.loads(path.read_text())
        symbols = payload.get('symbols', [])
        result: list[dict[str, Any]] = []
        for item in symbols:
            if not isinstance(item, dict):
                continue
            if not item.get('enabled', False):
                continue
            result.append(dict(item))
        return result


@dataclass(frozen=True)
class TigerProps:
    raw: dict[str, str]

    @property
    def tiger_id(self) -> str:
        return self.raw['tiger_id']

    @property
    def account(self) -> str:
        return self.raw['account']

    @property
    def private_key(self) -> str:
        return self.raw['private_key_pk8']

    @property
    def secret_key(self) -> str | None:
        return self.raw.get('secret_key') or self.raw.get('license')


def load_app_config(path: str | Path) -> AppConfig:
    return AppConfig(raw=json.loads(Path(path).read_text()))


def load_tiger_props(path: str | Path) -> TigerProps:
    data: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        data[k.strip()] = v.strip()
    required = ['tiger_id', 'account', 'private_key_pk8']
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise ValueError(f'missing tiger props: {missing}')
    return TigerProps(raw=data)
