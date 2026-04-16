from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


USER_SETTINGS_FILENAME = "user.settings.json"


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
    def broker(self) -> dict[str, Any]:
        return dict(self.raw.get('broker', {}))

    @property
    def broker_platform(self) -> str:
        broker = self.raw.get('broker', {})
        platform = broker.get('platform') if isinstance(broker, dict) else None
        return str(platform or 'tiger')

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
    return AppConfig(raw=load_app_config_raw(path))


def resolve_user_settings_path(path: str | Path, override: str | Path | None = None) -> Path:
    config_path = Path(path).resolve()
    env_override = os.environ.get("ENGINE_USER_SETTINGS")
    raw_override = env_override or override
    if raw_override:
        override_path = Path(raw_override)
        if not override_path.is_absolute():
            override_path = (config_path.parent / override_path).resolve()
        return override_path
    return config_path.parent / USER_SETTINGS_FILENAME


def load_user_settings(path: str | Path, override: str | Path | None = None) -> dict[str, Any]:
    settings_path = resolve_user_settings_path(path, override=override)
    if not settings_path.exists():
        return {}
    payload = json.loads(settings_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"user settings must be a JSON object: {settings_path}")
    return payload


def write_user_settings(path: str | Path, payload: dict[str, Any], override: str | Path | None = None) -> Path:
    settings_path = resolve_user_settings_path(path, override=override)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return settings_path


def merge_user_settings(path: str | Path, updates: dict[str, Any], override: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    merged = _deep_merge(load_user_settings(path, override=override), updates)
    settings_path = write_user_settings(path, merged, override=override)
    return merged, settings_path


def load_app_config_raw(path: str | Path, *, include_user_settings: bool = True, _seen: set[Path] | None = None) -> dict[str, Any]:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(config_path)

    seen = set() if _seen is None else _seen
    if config_path in seen:
        raise ValueError(f"cyclic config extends detected: {config_path}")
    seen.add(config_path)

    raw = json.loads(config_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"app config must be a JSON object: {config_path}")

    merged: dict[str, Any] = {}
    extends = raw.get("extends")
    user_settings_override = raw.get("user_settings")
    if extends:
        base_path = Path(extends)
        if not base_path.is_absolute():
            base_path = (config_path.parent / base_path).resolve()
        merged = load_app_config_raw(base_path, include_user_settings=False, _seen=seen)

    overlay = {
        key: value
        for key, value in raw.items()
        if key not in {"extends", "user_settings"}
    }
    merged = _deep_merge(merged, overlay)

    if include_user_settings:
        user_settings = load_user_settings(config_path, override=user_settings_override)
        merged = _deep_merge(merged, user_settings)

    return merged


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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
