from __future__ import annotations

from pathlib import Path

from ..data_cache import DataCache
from .broker import TigerClient
from .market_data import QuoteProvider, get_quote_provider


def get_broker_account_info(config_dir: str | Path) -> dict:
    return TigerClient(config_dir=config_dir).get_account_type()


def create_dashboard_bindings(
    *,
    broker_properties_dir: str | Path,
    config_dir: str | Path,
    provider_name: str,
    refresh_interval: int = 30,
) -> tuple[TigerClient, QuoteProvider, DataCache]:
    broker_client = TigerClient(config_dir=broker_properties_dir)
    quote_provider = get_quote_provider(
        provider_name,
        config_dir=str(config_dir),
        props_dir=str(broker_properties_dir),
    )
    cache = DataCache(broker_client, quote_provider, refresh_interval=refresh_interval)
    return broker_client, quote_provider, cache


def replace_quote_provider(
    cache: DataCache,
    provider_name: str,
    *,
    broker_properties_dir: str | Path,
    config_dir: str | Path,
) -> QuoteProvider:
    quote_provider = get_quote_provider(
        provider_name,
        config_dir=str(config_dir),
        props_dir=str(broker_properties_dir),
    )
    cache._quote_provider = quote_provider
    return quote_provider

