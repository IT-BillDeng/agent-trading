from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any

import urllib3
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .config import TigerProps

SERVER_URL = 'https://openapi.tigerfintech.com/gateway'
CHARSET = 'UTF-8'
SIGN_TYPE = 'RSA'


class TigerClient:
    def __init__(self, props: TigerProps):
        self.props = props
        self.http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED')

    def _device_id(self) -> str:
        raw = f'{uuid.getnode():012x}'
        return ':'.join(raw[i:i + 2] for i in range(0, 12, 2))

    def _fill_private_key_marker(self, private_key: str) -> bytes:
        return f'-----BEGIN PRIVATE KEY-----\n{private_key.strip()}\n-----END PRIVATE KEY-----\n'.encode()

    def _sign(self, sign_content: str) -> str:
        key = serialization.load_pem_private_key(
            self._fill_private_key_marker(self.props.private_key),
            password=None,
            backend=default_backend(),
        )
        signature = key.sign(sign_content.encode(CHARSET), padding.PKCS1v15(), hashes.SHA1())
        return base64.b64encode(signature).decode()

    def _sign_content(self, all_params: dict[str, Any]) -> str:
        parts = []
        for k, v in sorted(all_params.items()):
            parts.append(f'{k}={v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}')
        return '&'.join(parts)

    def request(self, method: str, biz_content: dict[str, Any] | None = None, version: str = '2.0') -> dict[str, Any]:
        params: dict[str, Any] = {
            'method': method,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tiger_id': self.props.tiger_id,
            'charset': CHARSET,
            'sign_type': SIGN_TYPE,
            'version': version,
            'device_id': self._device_id(),
        }
        if biz_content is not None:
            params['biz_content'] = json.dumps(biz_content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        params['sign'] = self._sign(self._sign_content(params))
        response = self.http.request(
            'POST',
            SERVER_URL,
            body=json.dumps(params).encode('utf-8'),
            headers={'Content-Type': f'application/json;charset={CHARSET}', 'User-Agent': 'agent-trading-engine/0.1'},
            timeout=15.0,
        )
        body = json.loads(response.data.decode(CHARSET, errors='replace'))
        return {'http_status': response.status, 'body': body}

    def get_accounts(self) -> dict[str, Any]:
        return self.request('accounts', {'account': self.props.account, 'lang': 'en_US'})

    def get_assets(self) -> dict[str, Any]:
        return self.request('assets', {'account': self.props.account})

    def get_positions(self) -> dict[str, Any]:
        return self.request('positions', {'account': self.props.account})

    def get_active_orders(self) -> dict[str, Any]:
        return self.request('active_orders', {'account': self.props.account, 'secret_key': self.props.secret_key, 'limit': 20})

    def get_inactive_orders(self, limit: int = 20) -> dict[str, Any]:
        return self.request('inactive_orders', {'account': self.props.account, 'secret_key': self.props.secret_key, 'limit': limit})

    def get_filled_orders(self, limit: int = 20) -> dict[str, Any]:
        return self.request('filled_orders', {'account': self.props.account, 'secret_key': self.props.secret_key, 'limit': limit})

    def get_order(self, id: int | None = None, order_id: int | None = None, show_charges: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {'account': self.props.account, 'secret_key': self.props.secret_key}
        if id is not None:
            payload['id'] = id
        if order_id is not None:
            payload['order_id'] = order_id
        if show_charges:
            payload['show_charges'] = True
        return self.request('orders', payload)

    def get_transactions(self, order_id: int | None = None, symbol: str | None = None, limit: int = 50) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'account': self.props.account,
            'secret_key': self.props.secret_key,
            'limit': limit,
        }
        if order_id is not None:
            payload['order_id'] = order_id
        if symbol is not None:
            payload['symbol'] = symbol
        return self.request('order_transactions', payload)

    def get_market_state(self, market: str) -> dict[str, Any]:
        return self.request('market_state', {'market': market, 'lang': 'en_US'})

    def get_quote_permission(self) -> dict[str, Any]:
        return self.request('get_quote_permission')

    def get_delay_quotes(self, symbols: list[str], market: str | None = None) -> dict[str, Any]:
        biz: dict[str, Any] = {'symbols': symbols, 'include_ask_bid': True}
        if market:
            biz['market'] = market
        return self.request('quote_delay', biz)

    def get_briefs(self, symbols: list[str], market: str | None = None) -> dict[str, Any]:
        biz: dict[str, Any] = {'symbols': symbols, 'include_ask_bid': True}
        if market:
            biz['market'] = market
        return self.request('brief', biz)

    def get_bars(self, symbols: list[str], period: str = '30min', limit: int = 30, 
                 begin_time: str | None = None, end_time: str | None = None) -> dict[str, Any]:
        """获取K线数据
        
        Args:
            symbols: 股票代码列表
            period: K线周期 (1min/5min/15min/30min/1hour/1day/1week/1month)
            limit: 返回K线数量 (最大500)
            begin_time: 开始时间 (yyyy-MM-dd HH:mm:ss)
            end_time: 结束时间 (yyyy-MM-dd HH:mm:ss)
        """
        biz = {'symbols': symbols, 'period': period, 'limit': limit}
        if begin_time:
            biz['begin_time'] = begin_time
        if end_time:
            biz['end_time'] = end_time
        return self.request('kline', biz)

    def create_order_no(self) -> dict[str, Any]:
        return self.request('order_no', {'account': self.props.account, 'secret_key': self.props.secret_key, 'lang': 'en_US'})

    def preview_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        merged = {'account': self.props.account, 'secret_key': self.props.secret_key, **payload}
        return self.request('preview_order', merged)

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        merged = {'account': self.props.account, 'secret_key': self.props.secret_key, **payload}
        return self.request('place_order', merged)

    def cancel_order(self, id: int | None = None, order_id: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {'account': self.props.account, 'secret_key': self.props.secret_key}
        if id is not None:
            payload['id'] = id
        if order_id is not None:
            payload['order_id'] = order_id
        return self.request('cancel_order', payload)

    def get_contract(self, symbol: str, market: str) -> dict[str, Any]:
        return self.request('contract', {'account': self.props.account, 'symbol': symbol, 'sec_type': 'STK', 'market': market, 'lang': 'zh_CN'}, version='3.0')
