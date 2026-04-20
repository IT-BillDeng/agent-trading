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
from .rule_engine import RuleEngine


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
    
    @property
    def total_cost(self) -> float:
        """总成本（含手续费和滑点）"""
        return self.price * self.quantity + self.commission + self.slippage
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    """持仓"""
    symbol: str
    quantity: int
    avg_cost: float
    entry_time: datetime
    current_price: float = 0.0
    
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
    
    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result['config'] = self.config.to_dict()
        result['start_time'] = self.start_time.isoformat()
        result['end_time'] = self.end_time.isoformat()
        return result


class DataFetcher:
    """历史数据获取器"""
    
    @staticmethod
    def fetch(symbol: str, start_date: str, end_date: str, 
              interval: str = '30m', source: str = 'yfinance') -> list[Bar]:
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
        if source == 'tiger':
            return DataFetcher._fetch_from_tiger(symbol, start_date, end_date, interval)
        else:
            return DataFetcher._fetch_from_yfinance(symbol, start_date, end_date, interval)
    
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
            # 如果时间跨度大，需要分批获取
            all_bars = []
            current_begin = begin_time
            
            while True:
                print(f"[DataFetcher] Fetching {symbol} from {current_begin} to {end_time}")
                resp = client.get_bars(
                    symbols=[symbol],
                    period=interval,
                    limit=500,
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
                
                for item in items:
                    # 数据源 K 线格式可能是列表或字典
                    if isinstance(item, dict):
                        # 字典格式: {'time': timestamp, 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
                        bar = Bar(
                            timestamp=datetime.fromtimestamp(item['time'] / 1000) if item.get('time', 0) > 1e10 else datetime.fromtimestamp(item.get('time', 0)),
                            open=float(item.get('open', 0)),
                            high=float(item.get('high', 0)),
                            low=float(item.get('low', 0)),
                            close=float(item.get('close', 0)),
                            volume=int(item.get('volume', 0))
                        )
                        all_bars.append(bar)
                    elif isinstance(item, list) and len(item) >= 6:
                        # 列表格式: [time, open, high, low, close, volume, ...]
                        bar = Bar(
                            timestamp=datetime.fromtimestamp(item[0] / 1000) if item[0] > 1e10 else datetime.fromtimestamp(item[0]),
                            open=float(item[1]),
                            high=float(item[2]),
                            low=float(item[3]),
                            close=float(item[4]),
                            volume=int(item[5])
                        )
                        all_bars.append(bar)
                
                # 检查是否已获取完
                if len(items) < 500:
                    break
                
                # 更新起始时间为最后一条K线的时间
                last_item = items[-1]
                if isinstance(last_item, dict):
                    last_time = last_item.get('time', 0)
                elif isinstance(last_item, list):
                    last_time = last_item[0] if last_item else 0
                else:
                    last_time = 0
                
                if last_time > 1e10:
                    current_begin = datetime.fromtimestamp(last_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    current_begin = datetime.fromtimestamp(last_time).strftime('%Y-%m-%d %H:%M:%S')
            
            # 去重并排序
            seen = set()
            unique_bars = []
            for bar in all_bars:
                key = bar.timestamp.isoformat()
                if key not in seen:
                    seen.add(key)
                    unique_bars.append(bar)
            
            unique_bars.sort(key=lambda b: b.timestamp)
            
            print(f"[DataFetcher] Broker: {len(unique_bars)} bars for {symbol}")
            return unique_bars
            
        except Exception as e:
            print(f"[DataFetcher] Broker failed for {symbol}: {e}")
            return []
    
    @staticmethod
    def fetch_multiple(symbols: list[str], start_date: str, end_date: str,
                       interval: str = '30m', source: str = 'yfinance') -> dict[str, list[Bar]]:
        """批量获取历史数据"""
        result = {}
        for symbol in symbols:
            result[symbol] = DataFetcher.fetch(symbol, start_date, end_date, interval, source)
        return result


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
        
        # 规则引擎
        self.rule_engine = RuleEngine(self.rules_path)
        
        # 历史数据
        self.bars_by_symbol: dict[str, list[Bar]] = {}
        self.current_index: dict[str, int] = {}

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
        
        self.bars_by_symbol = DataFetcher.fetch_multiple(
            self.config.symbols,
            self.config.start_date,
            self.config.end_date,
            interval,
            source=self.config.data_source
        )
        
        for symbol in self.config.symbols:
            self.current_index[symbol] = -1
            print(f"[Backtest] {symbol}: {len(self.bars_by_symbol.get(symbol, []))} bars loaded")
    
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
    
    def execute_trade(self, symbol: str, side: str, quantity: int, 
                      price: float, timestamp: datetime):
        """执行交易"""
        trade = self.order_simulator.simulate_order(
            symbol, side, quantity, price, timestamp
        )
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
                        current_price=price
                    )
        elif side == 'SELL':
            if symbol in self.positions:
                pos = self.positions[symbol]
                if quantity >= pos.quantity:
                    # 全部平仓
                    revenue = price * pos.quantity - trade.commission - trade.slippage
                    self.capital += revenue
                    del self.positions[symbol]
                else:
                    # 部分平仓
                    revenue = price * quantity - trade.commission - trade.slippage
                    self.capital += revenue
                    pos.quantity -= quantity
    
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
                    if signal.action == 'BUY' and symbol not in self.positions:
                        # 买入
                        quantity = self.calculate_position_size(symbol, bar.close)
                        self.execute_trade(symbol, 'BUY', quantity, bar.close, bar.timestamp)
                    
                    elif signal.action == 'EXIT' and symbol in self.positions:
                        # 卖出
                        pos = self.positions[symbol]
                        self.execute_trade(symbol, 'SELL', pos.quantity, bar.close, bar.timestamp)
            
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
        
        print(f"[Backtest] Completed: {result.total_trades} trades, {result.total_return_pct:.2f}% return")
        
        return result
    
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
        buy_trades = [t for t in self.trades if t.side == 'BUY']
        sell_trades = [t for t in self.trades if t.side == 'SELL']
        
        for sell in sell_trades:
            # 找到对应的买入交易
            matching_buys = [b for b in buy_trades if b.symbol == sell.symbol and b.timestamp < sell.timestamp]
            if matching_buys:
                buy = matching_buys[-1]  # 最近的买入
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
            equity_curve=self.equity_curve
        )


def run_backtest(config: BacktestConfig, rules_path: str | Path) -> BacktestResult:
    """运行回测"""
    engine = BacktestEngine(config, rules_path)
    return engine.run()
