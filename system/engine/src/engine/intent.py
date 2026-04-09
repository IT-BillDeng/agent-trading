from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass
class OrderIntent:
    intent_id: str
    cycle_id: str
    created_at: str
    mode: str
    symbol: str
    market: str
    side: str
    order_type: str
    quantity: int
    tif: str
    limit_price: float | None
    stop_price: float | None
    status: str
    idempotency_key: str
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntentBuilder:
    def __init__(self, app_config: dict[str, Any]):
        self.mode = str(app_config.get('mode', 'paper'))

    def build(self, previews: list[dict[str, Any]], cycle_id: str | None = None) -> list[OrderIntent]:
        cycle_id = cycle_id or self._cycle_id()
        intents: list[OrderIntent] = []
        for preview in previews:
            fingerprint = '|'.join([
                self.mode,
                preview['market'],
                preview['symbol'],
                preview['side'],
                preview['order_type'],
                str(preview['quantity']),
                str(preview.get('limit_price')),
                str(preview.get('stop_price')),
            ])
            idempotency_key = sha256(fingerprint.encode()).hexdigest()[:24]
            intents.append(OrderIntent(
                intent_id=f'intent-{idempotency_key}',
                cycle_id=cycle_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                mode=self.mode,
                symbol=preview['symbol'],
                market=preview['market'],
                side=preview['side'],
                order_type=preview['order_type'],
                quantity=int(preview['quantity']),
                tif=preview['tif'],
                limit_price=preview.get('limit_price'),
                stop_price=preview.get('stop_price'),
                status='DRY_RUN_READY',
                idempotency_key=idempotency_key,
                meta=dict(preview.get('meta', {})),
            ))
        return intents

    def _cycle_id(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
