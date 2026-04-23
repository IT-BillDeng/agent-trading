"""Broker adapter compatibility exports.

FF-01 only establishes the directory skeleton. Existing implementations remain
in their legacy modules and are surfaced here gradually. Heavy dependencies are
loaded lazily so the skeleton does not change import requirements.
"""

from ...broker_client import BrokerClient

__all__ = ["BrokerClient", "TigerClient"]


def __getattr__(name: str):
    if name == "TigerClient":
        from ...tiger_client import TigerClient

        return TigerClient
    raise AttributeError(name)
