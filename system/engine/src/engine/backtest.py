"""Backtest Framework - 回测框架"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import yfinance as yf

from .broker_fee import estimate_order_fee_breakdown, load_fee_schedule
from .market_sessions import classify_bar_session, parse_bar_timestamp, session_config
from .rule_engine import RuleEngine


class BacktestDataError(RuntimeError):
    """Raised when backtest market data is unavailable or internally inconsistent."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


@dataclass
class Bar:
    """K 线数据"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    def to_dict(self) -> dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


@dataclass
class Trade:
    """交易记录"""
    symbol: str
    side: str  # BUY / SELL
    quantity: int
    price: float
    timestamp: datetime
    commission: float = 0.0
    slippage: float = 0.0
    fee_breakdown: dict[str, float] = field(default_factory=dict)
    rule_id: str | None = None
    primary_rule_id: str | None = None
    base_rule_id: str | None = None
    symbol_profile: str | None = None
    effective_config_hash: str | None = None
    source_rule_ids: list[str] = field(default_factory=list)
    overrides_applied: dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_cost(self) -> float:
        """总成本（含手续费和滑点）"""
        return self.price * self.quantity + self.commission + self.slippage
    
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


@dataclass
class Position:
    """持仓"""
    symbol: str
    quantity: int
    avg_cost: float
    entry_time: datetime
    current_price: float = 0.0
    entry_rule_id: str | None = None
    entry_primary_rule_id: str | None = None
    entry_base_rule_id: str | None = None
    entry_symbol_profile: str | None = None
    entry_effective_config_hash: str | None = None
    entry_source_rule_ids: list[str] = field(default_factory=list)
    entry_overrides_applied: dict[str, Any] = field(default_factory=dict)
    entry_commission: float = 0.0
    entry_slippage: float = 0.0
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_cost) * self.quantity
    
    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost
    
    def to_dict(self) -> dict[str, Any]:
        return {
            'symbol': self.symbol,
            'quantity': self.quantity,
            'avg_cost': self.avg_cost,
            'entry_time': self.entry_time.isoformat(),
            'current_price': self.current_price,
            'market_value': self.market_value,
            'unrealized_pnl': self.unrealized_pnl,
            'unrealized_pnl_pct': self.unrealized_pnl_pct
        }


@dataclass
class BacktestConfig:
    """回测配置"""
    symbols: list[str]
    start_date: str
    end_date: str
    timeframe: str = '30min'
    initial_capital: float = 100000.0
    commission_rate: float = 0.001  # 0.1%
    slippage_rate: float = 0.001  # 0.1%
    broker_platform: str = 'tiger'
    market: str = 'US'
    fee_model: str = 'broker_default'
    max_position_pct: float = 0.2  # 单标的最大仓位比例
    data_source: str = 'tiger'  # 默认使用当前券商的历史数据提供器（兼容历史 provider 名）
    include_extended_hours: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    start_time: datetime
    end_time: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    commission_total: float
    slippage_total: float
    transaction_cost_total: float
    fee_drag_pct: float
    trades: list[Trade]
    equity_curve: list[dict[str, Any]]
    data_coverage: dict[str, Any] = field(default_factory=dict)
    data_warnings: list[str] = field(default_factory=list)
    attribution: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result['config'] = self.config.to_dict()
        result['start_time'] = self.start_time.isoformat()
        result['end_time'] = self.end_time.isoformat()
        result['trades'] = [trade.to_dict() for trade in self.trades]
        return result


class DataFetcher:
    """历史数据获取器"""

    TIGER_PAGE_LIMIT = 500
    TIGER_FALLBACK_SOURCE = 'yfinance'
    
    @staticmethod
    def fetch(symbol: str, start_date: str, end_date: str, 
              interval: str = '30m', source: str = 'yfinance', include_extended_hours: bool = False) -> list[Bar]:
        """
        获取历史数据
        
        Args:
            symbol: 标的代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            interval: 时间间隔 (1m, 5m, 15m, 30m, 1h, 1d)
            source: 数据源 ('yfinance' 或 'tiger')
        
        Returns:
            Bar 列表
        """
        bars, _meta = DataFetcher.fetch_with_metadata(
            symbol,
            start_date,
            end_date,
            interval=interval,
            source=source,
            include_extended_hours=include_extended_hours,
        )
        return bars

    @staticmethod
    def fetch_with_metadata(
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = '30m',
        source: str = 'yfinance',
        include_extended_hours: bool = False,
    ) -> tuple[list[Bar], dict[str, Any]]:
        requested_start = f"{start_date} 00:00:00"
        requested_end = f"{end_date} 23:59:59"
        fallback_used = False
        warnings: list[str] = []

        if source == 'tiger':
            try:
                bars = DataFetcher._fetch_from_tiger(symbol, start_date, end_date, interval)
                effective_source = 'tiger'
            except BacktestDataError as exc:
                warnings.append(str(exc))
                try:
                    bars = DataFetcher._fetch_from_yfinance(symbol, start_date, end_date, interval)
                    effective_source = DataFetcher.TIGER_FALLBACK_SOURCE
                    fallback_used = True
                    if bars:
                        warnings.append('tiger_fetch_failed_fallback_to_yfinance')
                    else:
                        raise BacktestDataError(
                            f"{symbol}: tiger fetch failed and yfinance fallback returned no bars",
                            diagnostics=exc.diagnostics,
                        ) from exc
                except BacktestDataError:
                    raise
                except Exception as fallback_exc:
                    raise BacktestDataError(
                        f"{symbol}: tiger fetch failed and yfinance fallback also failed: {fallback_exc}",
                        diagnostics=exc.diagnostics,
                    ) from fallback_exc
        else:
            bars = DataFetcher._fetch_from_yfinance(symbol, start_date, end_date, interval)
            effective_source = source

        filtered_bars = DataFetcher._filter_regular_session_bars(bars) if not include_extended_hours else bars
        status = 'ok' if filtered_bars else 'empty'
        if not filtered_bars and not warnings:
            warnings.append('no_bars_returned')
        metadata = DataFetcher._build_symbol_fetch_metadata(
            symbol,
            filtered_bars,
            data_source=effective_source,
            requested_start=requested_start,
            requested_end=requested_end,
            interval=interval,
            fallback_used=fallback_used,
            warnings=warnings,
            status=status,
        )
        return filtered_bars, metadata
    
    @staticmethod
    def _fetch_from_yfinance(symbol: str, start_date: str, end_date: str, 
                             interval: str = '30m') -> list[Bar]:
        """从 Yahoo Finance 获取历史数据（使用 yf.download 避免 v1.2.0 history() bug）"""
        try:
            df = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
            
            # yf.download 返回 MultiIndex columns 当多 symbol 时，单 symbol 时也可能有此问题
            if isinstance(df.columns, type(df.columns)) and df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)
            
            bars = []
            for index, row in df.iterrows():
                bar = Bar(
                    timestamp=index.to_pydatetime(),
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=int(row['Volume'])
                )
                bars.append(bar)
            
            return bars
        except Exception as e:
            print(f"[DataFetcher] yfinance failed for {symbol}: {e}")
            return []
    
    @staticmethod
    def _fetch_from_tiger(symbol: str, start_date: str, end_date: str,
                          interval: str = '30min') -> list[Bar]:
        """从当前 broker 的历史数据提供器获取历史数据"""
        try:
            from .tiger_client import TigerClient as DefaultBrokerClient
            from .config import load_tiger_props
            import os
            from pathlib import Path
            
            # 查找 broker 配置文件（优先专用目录，兼容旧 config 目录）
            props_dir = os.environ.get('BROKER_PROPERTIES_DIR') or os.environ.get('TIGER_PROPERTIES_DIR', None)
            if props_dir:
                props_file = Path(props_dir) / 'tiger_openapi_config.properties'
            else:
                config_dir = os.environ.get('TIGER_CONFIG_DIR', str(Path(__file__).parents[2] / 'config'))
                props_file = Path(config_dir) / 'tiger_openapi_config.properties'
            if not props_file.exists():
                props_file = Path(__file__).parents[2] / 'properties' / 'tiger_openapi_config.properties'
            
            if not props_file.exists():
                print(f"[DataFetcher] Broker config not found: {props_file}")
                return []
            
            props = load_tiger_props(props_file)
            client = DefaultBrokerClient(props)
            
            # 转换时间格式
            begin_time = f"{start_date} 00:00:00"
            end_time = f"{end_date} 23:59:59"
            
            # 当前数据源单次最多返回 500 根 K 线
            # 如果时间跨度大，需要分批获取，并确保分页严格前进
            all_bars = []
            current_begin = begin_time
            current_begin_dt = datetime.strptime(begin_time, '%Y-%m-%d %H:%M:%S')
            requested_end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            last_page_last_dt: datetime | None = None
            page_count = 0
            
            while True:
                page_count += 1
                print(f"[DataFetcher] Fetching {symbol} from {current_begin} to {end_time}")
                resp = client.get_bars(
                    symbols=[symbol],
                    period=interval,
                    limit=DataFetcher.TIGER_PAGE_LIMIT,
                    begin_time=current_begin,
                    end_time=end_time
                )
                
                # 检查 API 响应
                body = resp.get('body', {})
                code = body.get('code', -1)
                message = body.get('message', '')
                print(f"[DataFetcher] API response: code={code}, message={message}")
                
                if code != 0:
                    print(f"[DataFetcher] API error: {message}")
                    break
                
                data = body.get('data')
                if isinstance(data, str):
                    data = json.loads(data)
                
                if not data or not isinstance(data, list) or len(data) == 0:
                    print(f"[DataFetcher] No data returned for {symbol}")
                    break
                
                symbol_data = data[0]
                items = symbol_data.get('items', [])
                
                if not items:
                    break

                page_bars = DataFetcher._parse_tiger_items(symbol, items)
                if not page_bars:
                    raise BacktestDataError(
                        f"{symbol}: tiger returned malformed bar payload on page {page_count}",
                        diagnostics={
                            "symbol": symbol,
                            "data_source": "tiger",
                            "page": page_count,
                            "requested_start": begin_time,
                            "requested_end": end_time,
                        },
                    )

                page_bars = DataFetcher._dedupe_sort_bars(page_bars)
                page_first_dt = page_bars[0].timestamp
                page_last_dt = page_bars[-1].timestamp

                if last_page_last_dt is not None and page_last_dt <= last_page_last_dt:
                    raise BacktestDataError(
                        f"{symbol}: tiger pagination stalled at {page_last_dt.isoformat()}",
                        diagnostics={
                            "symbol": symbol,
                            "data_source": "tiger",
                            "page": page_count,
                            "requested_start": begin_time,
                            "requested_end": end_time,
                            "page_first_bar_time": page_first_dt.isoformat(),
                            "page_last_bar_time": page_last_dt.isoformat(),
                            "previous_last_bar_time": last_page_last_dt.isoformat(),
                        },
                    )

                new_page_bars = [
                    bar for bar in page_bars
                    if last_page_last_dt is None or bar.timestamp > last_page_last_dt
                ]
                if not new_page_bars:
                    raise BacktestDataError(
                        f"{symbol}: tiger pagination produced duplicate page at {page_last_dt.isoformat()}",
                        diagnostics={
                            "symbol": symbol,
                            "data_source": "tiger",
                            "page": page_count,
                            "requested_start": begin_time,
                            "requested_end": end_time,
                        },
                    )

                all_bars.extend(new_page_bars)
                last_page_last_dt = new_page_bars[-1].timestamp

                # 检查是否已获取完
                if len(items) < DataFetcher.TIGER_PAGE_LIMIT or last_page_last_dt >= requested_end_dt:
                    break

                next_begin_dt = last_page_last_dt + timedelta(seconds=1)
                if next_begin_dt <= current_begin_dt:
                    raise BacktestDataError(
                        f"{symbol}: tiger pagination cursor did not advance",
                        diagnostics={
                            "symbol": symbol,
                            "data_source": "tiger",
                            "page": page_count,
                            "requested_start": begin_time,
                            "requested_end": end_time,
                            "current_begin": current_begin_dt.isoformat(),
                            "next_begin": next_begin_dt.isoformat(),
                        },
                    )
                current_begin_dt = next_begin_dt
                current_begin = current_begin_dt.strftime('%Y-%m-%d %H:%M:%S')

            unique_bars = DataFetcher._dedupe_sort_bars(all_bars)
            
            print(f"[DataFetcher] Broker: {len(unique_bars)} bars for {symbol}")
            return unique_bars
            
        except BacktestDataError:
            raise
        except Exception as e:
            print(f"[DataFetcher] Broker failed for {symbol}: {e}")
            raise BacktestDataError(
                f"{symbol}: tiger fetch failed: {e}",
                diagnostics={
                    "symbol": symbol,
                    "data_source": "tiger",
                    "requested_start": start_date,
                    "requested_end": end_date,
                },
            ) from e
    
    @staticmethod
    def fetch_multiple(symbols: list[str], start_date: str, end_date: str,
                       interval: str = '30m', source: str = 'yfinance', include_extended_hours: bool = False) -> dict[str, list[Bar]]:
        """批量获取历史数据"""
        result = {}
        for symbol in symbols:
            result[symbol] = DataFetcher.fetch(
                symbol,
                start_date,
                end_date,
                interval,
                source,
                include_extended_hours=include_extended_hours,
            )
        return result

    @staticmethod
    def fetch_multiple_with_metadata(
        symbols: list[str],
        start_date: str,
        end_date: str,
        interval: str = '30m',
        source: str = 'yfinance',
        include_extended_hours: bool = False,
    ) -> tuple[dict[str, list[Bar]], dict[str, dict[str, Any]]]:
        result: dict[str, list[Bar]] = {}
        metadata: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            try:
                bars, symbol_meta = DataFetcher.fetch_with_metadata(
                    symbol,
                    start_date,
                    end_date,
                    interval=interval,
                    source=source,
                    include_extended_hours=include_extended_hours,
                )
                result[symbol] = bars
                metadata[symbol] = symbol_meta
            except BacktestDataError as exc:
                result[symbol] = []
                symbol_meta = dict(exc.diagnostics or {})
                symbol_meta.update(
                    DataFetcher._build_symbol_fetch_metadata(
                        symbol,
                        [],
                        data_source=source,
                        requested_start=f"{start_date} 00:00:00",
                        requested_end=f"{end_date} 23:59:59",
                        interval=interval,
                        status='error',
                        error=str(exc),
                    )
                )
                metadata[symbol] = symbol_meta
        return result, metadata

    @staticmethod
    def _filter_regular_session_bars(bars: list[Bar]) -> list[Bar]:
        session_cfg = session_config({"strategy": {"sessions": {"US": {}}}}, "US")
        filtered: list[Bar] = []
        for bar in bars:
            parsed = parse_bar_timestamp({"time": bar.timestamp.isoformat()}, timezone_name=session_cfg["timezone"])
            if parsed is None:
                continue
            if classify_bar_session(parsed, market="US", session_cfg=session_cfg) == "regular":
                filtered.append(bar)
        return filtered

    @staticmethod
    def _parse_tiger_items(symbol: str, items: list[Any]) -> list[Bar]:
        bars: list[Bar] = []
        for item in items:
            if isinstance(item, dict):
                raw_time = item.get('time', 0)
                bar = Bar(
                    timestamp=datetime.fromtimestamp(raw_time / 1000) if raw_time > 1e10 else datetime.fromtimestamp(raw_time),
                    open=float(item.get('open', 0)),
                    high=float(item.get('high', 0)),
                    low=float(item.get('low', 0)),
                    close=float(item.get('close', 0)),
                    volume=int(item.get('volume', 0)),
                )
                bars.append(bar)
            elif isinstance(item, list) and len(item) >= 6:
                raw_time = item[0]
                bar = Bar(
                    timestamp=datetime.fromtimestamp(raw_time / 1000) if raw_time > 1e10 else datetime.fromtimestamp(raw_time),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=int(item[5]),
                )
                bars.append(bar)
            else:
                print(f"[DataFetcher] Skipping malformed tiger item for {symbol}: {item!r}")
        return bars

    @staticmethod
    def _dedupe_sort_bars(bars: list[Bar]) -> list[Bar]:
        by_ts: dict[str, Bar] = {}
        for bar in bars:
            by_ts[bar.timestamp.isoformat()] = bar
        return [by_ts[key] for key in sorted(by_ts)]

    @staticmethod
    def _build_symbol_fetch_metadata(
        symbol: str,
        bars: list[Bar],
        *,
        data_source: str,
        requested_start: str,
        requested_end: str,
        interval: str,
        fallback_used: bool = False,
        warnings: list[str] | None = None,
        status: str = 'ok',
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "bars_count": len(bars),
            "first_bar_time": bars[0].timestamp.isoformat() if bars else None,
            "last_bar_time": bars[-1].timestamp.isoformat() if bars else None,
            "data_source": data_source,
            "requested_start": requested_start,
            "requested_end": requested_end,
            "requested_interval": interval,
            "fallback_used": fallback_used,
            "status": status,
            "warnings": list(warnings or []),
            "error": error,
        }


class OrderSimulator:
    """订单撮合模拟器"""
    
    def __init__(
        self,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.001,
        *,
        broker_platform: str = 'tiger',
        market: str = 'US',
        fee_model: str = 'broker_default',
        fee_schedule: dict[str, Any] | None = None,
    ):
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.broker_platform = broker_platform
        self.market = market
        self.fee_model = fee_model
        self.fee_schedule = fee_schedule or {}
    
    def calculate_commission(self, price: float, quantity: int, side: str) -> float:
        """计算手续费总额。默认优先使用 broker-specific fee model。"""
        if self.fee_model == 'broker_default':
            breakdown = self.calculate_fee_breakdown(price, quantity, side)
            if breakdown:
                return round(sum(breakdown.values()), 6)
        return price * quantity * self.commission_rate

    def calculate_fee_breakdown(self, price: float, quantity: int, side: str) -> dict[str, float]:
        if self.fee_model != 'broker_default':
            return {}
        return estimate_order_fee_breakdown(
            broker_platform=self.broker_platform,
            market=self.market,
            side=side,
            price=price,
            quantity=quantity,
            fee_schedule=self.fee_schedule,
        )
    
    def calculate_slippage(self, price: float, quantity: int, side: str) -> float:
        """计算滑点"""
        # 买入时滑点增加成本，卖出时滑点减少收入
        slippage_amount = price * self.slippage_rate
        if side == 'BUY':
            return slippage_amount * quantity
        else:
            return -slippage_amount * quantity
    
    def simulate_order(self, symbol: str, side: str, quantity: int, 
                       price: float, timestamp: datetime) -> Trade:
        """模拟订单执行"""
        fee_breakdown = self.calculate_fee_breakdown(price, quantity, side)
        commission = self.calculate_commission(price, quantity, side)
        slippage = self.calculate_slippage(price, quantity, side)
        
        return Trade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            commission=commission,
            slippage=abs(slippage),
            fee_breakdown=fee_breakdown,
        )


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, config: BacktestConfig, rules_path: str | Path):
        self.config = config
        self.rules_path = Path(rules_path)
        self.order_simulator = OrderSimulator(
            commission_rate=config.commission_rate,
            slippage_rate=config.slippage_rate,
            broker_platform=config.broker_platform,
            market=config.market,
            fee_model=config.fee_model,
            fee_schedule=self._load_fee_schedule(config.broker_platform),
        )
        
        # 状态
        self.capital = config.initial_capital
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.closed_trade_records: list[dict[str, Any]] = []
        self.signal_attribution: dict[str, dict[str, dict[str, Any]]] = {}
        self.attribution_unknown: list[dict[str, Any]] = []
        
        # 规则引擎
        self.rule_engine = RuleEngine(self.rules_path, symbol_universe=config.symbols)
        self.symbol_profile_overview = self.rule_engine.get_symbol_profile_overview(
            config.symbols,
            market_by_symbol={symbol: config.market for symbol in config.symbols},
        )
        
        # 历史数据
        self.bars_by_symbol: dict[str, list[Bar]] = {}
        self.current_index: dict[str, int] = {}
        self.data_coverage: dict[str, dict[str, Any]] = {}
        self.data_warnings: list[str] = []

    @staticmethod
    def _load_fee_schedule(broker_platform: str) -> dict[str, Any]:
        payload = load_fee_schedule(broker_platform)
        if not payload:
            print(f"[Backtest] No fee schedule found for broker {broker_platform}")
        return payload
    
    def load_data(self):
        """加载历史数据"""
        print(f"[Backtest] Loading data for {len(self.config.symbols)} symbols...")
        print(f"[Backtest] Data source: {self.config.data_source}")
        
        # 转换时间间隔格式
        interval = self.config.timeframe
        if self.config.data_source == 'yfinance':
            interval_map = {
                '1min': '1m',
                '5min': '5m',
                '15min': '15m',
                '30min': '30m',
                '60min': '1h',
                '1h': '1h',
                '1d': '1d'
            }
            interval = interval_map.get(self.config.timeframe, '30m')
        
        self.bars_by_symbol, self.data_coverage = DataFetcher.fetch_multiple_with_metadata(
            self.config.symbols,
            self.config.start_date,
            self.config.end_date,
            interval,
            source=self.config.data_source,
            include_extended_hours=self.config.include_extended_hours,
        )
        self.data_warnings = []

        for symbol in self.config.symbols:
            self.current_index[symbol] = -1
            symbol_meta = self.data_coverage.get(symbol, {})
            bars_count = int(symbol_meta.get("bars_count", len(self.bars_by_symbol.get(symbol, []))))
            print(
                f"[Backtest] {symbol}: bars={bars_count}, "
                f"first={symbol_meta.get('first_bar_time')}, "
                f"last={symbol_meta.get('last_bar_time')}, "
                f"source={symbol_meta.get('data_source')}, "
                f"requested={symbol_meta.get('requested_start')} -> {symbol_meta.get('requested_end')}"
            )
            if symbol_meta.get("warnings"):
                self.data_warnings.extend([f"{symbol}: {item}" for item in symbol_meta["warnings"]])
            if symbol_meta.get("error"):
                self.data_warnings.append(f"{symbol}: {symbol_meta['error']}")

            required_bars = self._required_bars_for_symbol(symbol)
            symbol_meta["required_bars"] = required_bars
            symbol_meta["has_sufficient_bars"] = bars_count >= required_bars
            if bars_count < required_bars:
                self.data_warnings.append(f"{symbol}: insufficient_bars ({bars_count}/{required_bars})")

        if all(int(meta.get("bars_count", 0)) == 0 for meta in self.data_coverage.values()):
            raise BacktestDataError(
                "No valid bars loaded for any symbol in backtest window",
                diagnostics={"symbols": self.data_coverage},
            )

        if not any(bool(meta.get("has_sufficient_bars")) for meta in self.data_coverage.values()):
            raise BacktestDataError(
                "Bars loaded but insufficient for all symbols in backtest window",
                diagnostics={"symbols": self.data_coverage},
            )
    
    def get_current_bar(self, symbol: str) -> Bar | None:
        """获取当前 K 线"""
        bars = self.bars_by_symbol.get(symbol, [])
        index = self.current_index.get(symbol, 0)
        if 0 <= index < len(bars):
            return bars[index]
        return None
    
    def get_bars_history(self, symbol: str, lookback: int = 50) -> list[dict[str, Any]]:
        """获取历史 K 线数据（用于指标计算）"""
        bars = self.bars_by_symbol.get(symbol, [])
        index = self.current_index.get(symbol, 0)
        if index < 0:
            return []
        start = max(0, index - lookback + 1)
        end = index + 1
        
        history = []
        for bar in bars[start:end]:
            history.append(bar.to_dict())
        
        return history
    
    def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        timestamp: datetime,
        *,
        signal=None,
    ):
        """执行交易"""
        trade = self.order_simulator.simulate_order(
            symbol, side, quantity, price, timestamp
        )
        if signal is not None:
            trade.rule_id = getattr(signal, "rule_id", None)
            trade.primary_rule_id = getattr(signal, "primary_rule_id", None) or getattr(signal, "rule_id", None)
            trade.base_rule_id = getattr(signal, "base_rule_id", None) or getattr(signal, "rule_id", None)
            trade.symbol_profile = getattr(signal, "symbol_profile", None)
            trade.effective_config_hash = getattr(signal, "effective_config_hash", None)
            trade.source_rule_ids = list(getattr(signal, "source_rule_ids", []) or [])
            trade.overrides_applied = dict(getattr(signal, "overrides_applied", {}) or {})
        self.trades.append(trade)
        
        if side == 'BUY':
            cost = trade.total_cost
            if cost <= self.capital:
                self.capital -= cost
                if symbol in self.positions:
                    # 加仓
                    pos = self.positions[symbol]
                    total_cost = pos.avg_cost * pos.quantity + price * quantity
                    total_quantity = pos.quantity + quantity
                    pos.avg_cost = total_cost / total_quantity
                    pos.quantity = total_quantity
                else:
                    # 新建仓
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=quantity,
                        avg_cost=price,
                        entry_time=timestamp,
                        current_price=price,
                        entry_rule_id=trade.rule_id,
                        entry_primary_rule_id=trade.primary_rule_id,
                        entry_base_rule_id=trade.base_rule_id,
                        entry_symbol_profile=trade.symbol_profile,
                        entry_effective_config_hash=trade.effective_config_hash,
                        entry_source_rule_ids=list(trade.source_rule_ids),
                        entry_overrides_applied=dict(trade.overrides_applied),
                        entry_commission=trade.commission,
                        entry_slippage=trade.slippage,
                    )
        elif side == 'SELL':
            if symbol in self.positions:
                pos = self.positions[symbol]
                fraction = quantity / pos.quantity if pos.quantity > 0 else 0.0
                if quantity >= pos.quantity:
                    # 全部平仓
                    revenue = price * pos.quantity - trade.commission - trade.slippage
                    self.capital += revenue
                    self._record_closed_trade(pos, trade, quantity=pos.quantity)
                    del self.positions[symbol]
                else:
                    # 部分平仓
                    revenue = price * quantity - trade.commission - trade.slippage
                    self.capital += revenue
                    self._record_closed_trade(pos, trade, quantity=quantity)
                    pos.quantity -= quantity
                    pos.entry_commission *= max(0.0, 1 - fraction)
                    pos.entry_slippage *= max(0.0, 1 - fraction)
    
    def calculate_position_size(self, symbol: str, price: float) -> int:
        """计算仓位大小"""
        max_position_value = self.capital * self.config.max_position_pct
        max_quantity = int(max_position_value / price)
        return max(1, max_quantity)
    
    def update_equity(self, timestamp: datetime):
        """更新权益曲线"""
        total_value = self.capital
        
        for symbol, pos in self.positions.items():
            bar = self.get_current_bar(symbol)
            if bar:
                pos.current_price = bar.close
                total_value += pos.market_value
        
        self.equity_curve.append({
            'timestamp': timestamp.isoformat(),
            'cash': self.capital,
            'positions_value': total_value - self.capital,
            'total_value': total_value
        })
    
    def run(self) -> BacktestResult:
        """运行回测"""
        print(f"[Backtest] Starting backtest from {self.config.start_date} to {self.config.end_date}")
        
        self.load_data()
        
        all_timestamps = sorted(
            {
                bar.timestamp
                for bars in self.bars_by_symbol.values()
                for bar in bars
            }
        )

        start_time = datetime.now()

        for i, timestamp in enumerate(all_timestamps):
            for symbol in self.config.symbols:
                bars = self.bars_by_symbol.get(symbol, [])
                next_index = self.current_index.get(symbol, -1) + 1
                if next_index >= len(bars):
                    continue
                if bars[next_index].timestamp != timestamp:
                    continue

                self.current_index[symbol] = next_index
                bar = bars[next_index]
                
                # 更新持仓价格
                if symbol in self.positions:
                    self.positions[symbol].current_price = bar.close
                
                # 获取历史数据并评估规则
                bars_history = self.get_bars_history(symbol)
                position = self.positions.get(symbol)
                position_dict = position.to_dict() if position else None
                
                signals = self.rule_engine.evaluate_symbol(symbol, 'US', bars_history, position_dict)
                
                for signal in signals:
                    self._record_signal(signal)
                    if signal.action == 'BUY' and symbol not in self.positions:
                        # 买入
                        quantity = self.calculate_position_size(symbol, bar.close)
                        self.execute_trade(symbol, 'BUY', quantity, bar.close, bar.timestamp, signal=signal)
                        self._record_entry(signal)
                    
                    elif signal.action == 'EXIT' and symbol in self.positions:
                        # 卖出
                        pos = self.positions[symbol]
                        self.execute_trade(symbol, 'SELL', pos.quantity, bar.close, bar.timestamp, signal=signal)
                        self._record_exit(signal)
            
            # 更新权益曲线
            if i % 10 == 0:  # 每 10 根 K 线记录一次
                self.update_equity(timestamp)

        if all_timestamps:
            last_timestamp = all_timestamps[-1]
            if not self.equity_curve or self.equity_curve[-1]['timestamp'] != last_timestamp.isoformat():
                self.update_equity(last_timestamp)
        
        end_time = datetime.now()
        
        # 计算最终权益
        final_equity = self.equity_curve[-1]['total_value'] if self.equity_curve else self.capital
        
        # 计算绩效指标
        result = self.calculate_performance(start_time, end_time, final_equity)
        result.attribution = self._build_attribution()
        result.data_coverage = self.data_coverage
        result.data_warnings = self.data_warnings
        
        print(f"[Backtest] Completed: {result.total_trades} trades, {result.total_return_pct:.2f}% return")
        
        return result

    def _required_bars_for_symbol(self, symbol: str) -> int:
        enabled_rules = self.rule_engine.get_enabled_rules(symbol=symbol, market=self.config.market)
        if not enabled_rules:
            return 10
        return max(self.rule_engine._get_min_bars_required(rule) for rule in enabled_rules)
    
    def calculate_performance(self, start_time: datetime, end_time: datetime, 
                              final_capital: float) -> BacktestResult:
        """计算绩效指标"""
        total_return = final_capital - self.config.initial_capital
        total_return_pct = (total_return / self.config.initial_capital) * 100
        
        # 交易统计
        total_trades = len(self.trades)
        winning_trades = 0
        losing_trades = 0
        total_win = 0.0
        total_loss = 0.0
        
        # 简化计算：假设每对买卖交易计算盈亏
        if self.closed_trade_records:
            for trade_record in self.closed_trade_records:
                pnl = float(trade_record.get("net_pnl", 0.0) or 0.0)
                if pnl > 0:
                    winning_trades += 1
                    total_win += pnl
                else:
                    losing_trades += 1
                    total_loss += abs(pnl)
        else:
            buy_trades = [t for t in self.trades if t.side == 'BUY']
            sell_trades = [t for t in self.trades if t.side == 'SELL']

            for sell in sell_trades:
                matching_buys = [b for b in buy_trades if b.symbol == sell.symbol and b.timestamp < sell.timestamp]
                if matching_buys:
                    buy = matching_buys[-1]
                    pnl = (
                        (sell.price - buy.price) * sell.quantity
                        - sell.commission
                        - buy.commission
                        - sell.slippage
                        - buy.slippage
                    )
                    if pnl > 0:
                        winning_trades += 1
                        total_win += pnl
                    else:
                        losing_trades += 1
                        total_loss += abs(pnl)
        
        closed_trades = winning_trades + losing_trades
        win_rate = winning_trades / closed_trades if closed_trades > 0 else 0.0
        avg_win = total_win / winning_trades if winning_trades > 0 else 0.0
        avg_loss = total_loss / losing_trades if losing_trades > 0 else 0.0
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
        
        # 计算最大回撤
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        peak_value = self.config.initial_capital
        
        for point in self.equity_curve:
            value = point['total_value']
            if value > peak_value:
                peak_value = value
            drawdown = peak_value - value
            drawdown_pct = (drawdown / peak_value) * 100 if peak_value > 0 else 0.0
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct
        
        # 计算夏普比率（简化版）
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i-1]['total_value']
            curr = self.equity_curve[i]['total_value']
            if prev > 0:
                returns.append((curr - prev) / prev)
        
        if returns:
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe_ratio = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        commission_total = round(sum(trade.commission for trade in self.trades), 6)
        slippage_total = round(sum(trade.slippage for trade in self.trades), 6)
        transaction_cost_total = round(commission_total + slippage_total, 6)
        fee_drag_pct = (transaction_cost_total / self.config.initial_capital) * 100 if self.config.initial_capital > 0 else 0.0
        
        return BacktestResult(
            config=self.config,
            start_time=start_time,
            end_time=end_time,
            initial_capital=self.config.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            commission_total=commission_total,
            slippage_total=slippage_total,
            transaction_cost_total=transaction_cost_total,
            fee_drag_pct=fee_drag_pct,
            trades=self.trades,
            equity_curve=self.equity_curve,
        )

    def _record_signal(self, signal) -> None:
        action = str(getattr(signal, "action", "HOLD") or "HOLD").upper()
        if action not in {"BUY", "EXIT"}:
            return
        self._metric_for_signal(signal)["signals"] += 1

    def _record_entry(self, signal) -> None:
        action = str(getattr(signal, "action", "HOLD") or "HOLD").upper()
        if action == "BUY":
            self._metric_for_signal(signal)["entries"] += 1

    def _record_exit(self, signal) -> None:
        action = str(getattr(signal, "action", "HOLD") or "HOLD").upper()
        if action == "EXIT":
            self._metric_for_signal(signal)["exits"] += 1

    def _metric_for_signal(self, signal) -> dict[str, Any]:
        symbol = str(getattr(signal, "symbol", "") or "")
        rule_id = str(getattr(signal, "primary_rule_id", None) or getattr(signal, "rule_id", "unknown"))
        profile = getattr(signal, "symbol_profile", None) or self.symbol_profile_overview.get(symbol, {}).get("profile") or "unknown"
        return self._ensure_attribution_metric(symbol, rule_id, profile=profile)

    def _ensure_attribution_metric(self, symbol: str, rule_id: str, *, profile: str) -> dict[str, Any]:
        symbol_bucket = self.signal_attribution.setdefault(symbol, {})
        metric = symbol_bucket.get(rule_id)
        if not isinstance(metric, dict):
            metric = {
                "profile": profile,
                "signals": 0,
                "entries": 0,
                "exits": 0,
                "closed_trades": 0,
                "winning_closed_trades": 0,
                "gross_pnl": 0.0,
                "net_pnl": 0.0,
                "commission_total": 0.0,
                "slippage_total": 0.0,
                "transaction_cost_total": 0.0,
                "drawdown_curve": [],
            }
            symbol_bucket[rule_id] = metric
        return metric

    def _record_closed_trade(self, position: Position, sell_trade: Trade, *, quantity: int) -> None:
        rule_id = position.entry_primary_rule_id or position.entry_rule_id
        if not rule_id:
            self.attribution_unknown.append(
                {
                    "kind": "closed_trade_missing_primary_rule_id",
                    "symbol": position.symbol,
                    "timestamp": sell_trade.timestamp.isoformat(),
                }
            )
            return

        buy_commission = float(position.entry_commission or 0.0)
        buy_slippage = float(position.entry_slippage or 0.0)
        sell_commission = float(sell_trade.commission or 0.0)
        sell_slippage = float(sell_trade.slippage or 0.0)
        gross_pnl = (sell_trade.price - position.avg_cost) * quantity
        transaction_cost_total = buy_commission + buy_slippage + sell_commission + sell_slippage
        net_pnl = gross_pnl - transaction_cost_total

        metric = self._ensure_attribution_metric(
            position.symbol,
            str(rule_id),
            profile=position.entry_symbol_profile or "unknown",
        )
        metric["closed_trades"] += 1
        metric["winning_closed_trades"] += 1 if net_pnl > 0 else 0
        metric["gross_pnl"] += gross_pnl
        metric["net_pnl"] += net_pnl
        metric["commission_total"] += buy_commission + sell_commission
        metric["slippage_total"] += buy_slippage + sell_slippage
        metric["transaction_cost_total"] += transaction_cost_total
        metric["drawdown_curve"].append(net_pnl)

        self.closed_trade_records.append(
            {
                "symbol": position.symbol,
                "rule_id": position.entry_rule_id,
                "primary_rule_id": position.entry_primary_rule_id,
                "base_rule_id": position.entry_base_rule_id,
                "symbol_profile": position.entry_symbol_profile,
                "effective_config_hash": position.entry_effective_config_hash,
                "source_rule_ids": list(position.entry_source_rule_ids),
                "overrides_applied": dict(position.entry_overrides_applied),
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "commission_total": buy_commission + sell_commission,
                "slippage_total": buy_slippage + sell_slippage,
                "transaction_cost_total": transaction_cost_total,
                "entry_time": position.entry_time.isoformat(),
                "exit_time": sell_trade.timestamp.isoformat(),
            }
        )

    def _build_attribution(self) -> dict[str, Any]:
        symbols_payload: dict[str, Any] = {}
        rules_payload: dict[str, Any] = {}

        for symbol in self.config.symbols:
            overview = self.symbol_profile_overview.get(symbol, {})
            profile = overview.get("profile") or "unknown"
            rules_meta = overview.get("rules", {}) if isinstance(overview.get("rules"), dict) else {}
            rule_entries: dict[str, Any] = {}

            for rule_id in rules_meta.keys():
                metric = self._ensure_attribution_metric(symbol, rule_id, profile=profile)
                rule_entries[rule_id] = self._finalize_attribution_metric(metric)

            symbols_payload[symbol] = {
                "profile": profile,
                "rules": rule_entries,
            }

        aggregated_by_rule: dict[str, dict[str, Any]] = {}
        for symbol, rules in self.signal_attribution.items():
            for rule_id, metric in rules.items():
                agg = aggregated_by_rule.setdefault(
                    rule_id,
                    {
                        "symbols": [],
                        "signals": 0,
                        "entries": 0,
                        "exits": 0,
                        "closed_trades": 0,
                        "winning_closed_trades": 0,
                        "gross_pnl": 0.0,
                        "net_pnl": 0.0,
                        "commission_total": 0.0,
                        "slippage_total": 0.0,
                        "transaction_cost_total": 0.0,
                        "drawdown_curve": [],
                    },
                )
                if symbol not in agg["symbols"]:
                    agg["symbols"].append(symbol)
                for key in ("signals", "entries", "exits", "closed_trades", "winning_closed_trades"):
                    agg[key] += metric.get(key, 0)
                for key in ("gross_pnl", "net_pnl", "commission_total", "slippage_total", "transaction_cost_total"):
                    agg[key] += float(metric.get(key, 0.0) or 0.0)
                agg["drawdown_curve"].extend(metric.get("drawdown_curve", []))

        for rule_id, metric in aggregated_by_rule.items():
            rules_payload[rule_id] = {
                "symbols": metric["symbols"],
                **self._finalize_attribution_metric(metric),
            }

        attribution = {
            "symbols": symbols_payload,
            "rules": rules_payload,
        }
        if self.attribution_unknown:
            attribution["attribution_unknown"] = self.attribution_unknown
        return attribution

    def _finalize_attribution_metric(self, metric: dict[str, Any]) -> dict[str, Any]:
        closed_trades = int(metric.get("closed_trades", 0) or 0)
        winning_closed_trades = int(metric.get("winning_closed_trades", 0) or 0)
        commission_total = round(float(metric.get("commission_total", 0.0) or 0.0), 6)
        slippage_total = round(float(metric.get("slippage_total", 0.0) or 0.0), 6)
        transaction_cost_total = round(float(metric.get("transaction_cost_total", 0.0) or 0.0), 6)
        gross_pnl = float(metric.get("gross_pnl", 0.0) or 0.0)
        net_pnl = float(metric.get("net_pnl", 0.0) or 0.0)
        return {
            "signals": int(metric.get("signals", 0) or 0),
            "entries": int(metric.get("entries", 0) or 0),
            "exits": int(metric.get("exits", 0) or 0),
            "closed_trades": closed_trades,
            "winning_closed_trades": winning_closed_trades,
            "win_rate": (winning_closed_trades / closed_trades) if closed_trades > 0 else None,
            "gross_return_pct": round((gross_pnl / self.config.initial_capital) * 100, 6) if self.config.initial_capital > 0 else 0.0,
            "net_return_pct": round((net_pnl / self.config.initial_capital) * 100, 6) if self.config.initial_capital > 0 else 0.0,
            "commission_total": commission_total,
            "slippage_total": slippage_total,
            "transaction_cost_total": transaction_cost_total,
            "fee_drag_pct": round((transaction_cost_total / self.config.initial_capital) * 100, 6) if self.config.initial_capital > 0 else 0.0,
            "max_drawdown_pct": round(self._drawdown_pct(metric.get("drawdown_curve", [])), 6),
        }

    def _drawdown_pct(self, realized_pnl_curve: list[float]) -> float:
        if not realized_pnl_curve or self.config.initial_capital <= 0:
            return 0.0
        peak = self.config.initial_capital
        equity = self.config.initial_capital
        max_drawdown = 0.0
        for delta in realized_pnl_curve:
            equity += float(delta or 0.0)
            if equity > peak:
                peak = equity
            if peak > 0:
                max_drawdown = max(max_drawdown, ((peak - equity) / peak) * 100)
        return max_drawdown


def run_backtest(config: BacktestConfig, rules_path: str | Path) -> BacktestResult:
    """运行回测"""
    engine = BacktestEngine(config, rules_path)
    return engine.run()
