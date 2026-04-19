"""Closer - 收盘总结生成器"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

from .artifacts import append_jsonl, resolve_artifacts_root, write_json


# 时区定义
TZ_US = timezone(timedelta(hours=-4))  # ET (假设 EDT)


class DashboardAPIClient:
    """Dashboard API 客户端"""
    
    def __init__(self, base_url: str = "http://host.docker.internal:8088"):
        self.base_url = base_url.rstrip("/")
    
    def get(self, endpoint: str, timeout: int = 10) -> dict[str, Any]:
        """GET 请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}


@dataclass
class CloserSummary:
    """收盘总结"""
    market: str
    date: str
    cycle_count: int
    signals: dict[str, int]
    orders: dict[str, int]
    account: dict[str, Any]
    positions: list[dict[str, Any]]
    risk_blockers: list[dict[str, Any]]
    focus_symbols: list[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "date": self.date,
            "cycle_count": self.cycle_count,
            "signals": self.signals,
            "orders": self.orders,
            "account": self.account,
            "positions": self.positions,
            "risk_blockers": self.risk_blockers,
            "focus_symbols": self.focus_symbols
        }


def check_has_trading_data(client: DashboardAPIClient, market: str) -> bool:
    """检查当天是否有交易数据（判断是否交易日）"""
    try:
        # 检查最近的执行周期是否有数据
        data = client.get("/api/engine")
        
        if "error" in data:
            return True  # API 不可达，默认运行
        
        cycle = data.get("last_cycle")
        if not cycle:
            return False  # 无执行周期，可能是休市
        
        # 检查周期时间是否是今天的
        cycle_id = cycle.get("cycle_id", "")
        today = datetime.now().strftime("%Y%m%d")
        
        if today in cycle_id:
            return True  # 今天有执行周期
        
        # 检查信号是否有数据
        signals = cycle.get("strategy", {}).get("signals", [])
        if signals:
            return True
        
        return False
    except Exception:
        return True


class TigerCloser:
    """收盘总结生成器"""
    
    def __init__(self, base_url: str = "http://host.docker.internal:8088"):
        self.client = DashboardAPIClient(base_url)
    
    def get_engine_data(self) -> dict[str, Any]:
        """获取引擎数据"""
        return self.client.get("/api/engine")
    
    def get_signals(self) -> dict[str, Any]:
        """获取信号数据"""
        return self.client.get("/api/signals")
    
    def get_account(self) -> dict[str, Any]:
        """获取账户状态"""
        return self.client.get("/api/account")
    
    def get_positions(self) -> list[dict[str, Any]]:
        """获取持仓信息"""
        data = self.client.get("/api/positions")
        if isinstance(data, list):
            return data
        return data.get("positions", [])
    
    def get_orders(self) -> list[dict[str, Any]]:
        """获取订单记录"""
        data = self.client.get("/api/orders")
        if isinstance(data, list):
            return data
        return data.get("orders", [])
    
    def get_watchlist(self) -> dict[str, Any]:
        """获取自选列表"""
        return self.client.get("/api/watchlist")
    
    def generate_summary(self, market: str) -> CloserSummary:
        """生成收盘总结"""
        # 获取当前日期
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        
        # 获取数据
        engine = self.get_engine_data()
        signals = self.get_signals()
        account = self.get_account()
        positions = self.get_positions()
        orders = self.get_orders()
        
        # 分析信号
        signal_list = signals.get("signals", [])
        buy_count = len([s for s in signal_list if s.get("action") == "BUY"])
        exit_count = len([s for s in signal_list if s.get("action") == "EXIT"])
        hold_count = len([s for s in signal_list if s.get("action") == "HOLD"])
        
        # 分析订单
        filled_orders = [o for o in orders if o.get("status") == "Filled"]
        pending_orders = [o for o in orders if o.get("status") in ("Submitted", "Pending")]
        
        # 获取风控信息
        risk = engine.get("last_cycle", {}).get("risk", {})
        blockers = risk.get("preview_blockers", [])
        
        # 确定关注标的
        focus_symbols = []
        for s in signal_list:
            if s.get("action") == "BUY":
                focus_symbols.append(s.get("symbol"))
        
        # 如果没有信号，关注有持仓的标的
        if not focus_symbols and positions:
            focus_symbols = [p.get("symbol") for p in positions[:3]]
        
        # 如果还没有，关注自选列表前几个
        if not focus_symbols:
            watchlist = self.get_watchlist()
            symbols = watchlist.get("symbols", [])
            focus_symbols = [s.get("symbol") for s in symbols if s.get("enabled")][:3]
        
        return CloserSummary(
            market=market,
            date=date_str,
            cycle_count=engine.get("last_cycle", {}).get("cycle_id", "N/A"),
            signals={"buy": buy_count, "exit": exit_count, "hold": hold_count},
            orders={"filled": len(filled_orders), "pending": len(pending_orders)},
            account={
                "net_liquidation": account.get("net_liquidation", account.get("total_assets")),
                "unrealized_pnl": account.get("unrealized_pnl"),
                "cash": account.get("cash", account.get("cash_balance"))
            },
            positions=positions,
            risk_blockers=blockers,
            focus_symbols=focus_symbols
        )
    
    def format_report(self, summary: CloserSummary) -> str:
        """格式化报告"""
        account = summary.account
        net_liq = account.get("net_liquidation") or 0
        unrealized_pnl = account.get("unrealized_pnl") or 0
        cash = account.get("cash") or 0
        
        # 计算盈亏百分比
        pnl_pct = ""
        if net_liq and unrealized_pnl is not None:
            try:
                pct = (unrealized_pnl / net_liq) * 100
                pnl_pct = f" ({pct:+.2f}%)"
            except Exception:
                pass
        
        # 持仓信息
        position_lines = []
        for p in summary.positions[:5]:  # 最多显示5个
            symbol = p.get("symbol", "?")
            qty = p.get("quantity", 0)
            pnl = p.get("unrealized_pnl", 0) or 0
            position_lines.append(f"  • {symbol}: {qty}股, 浮盈亏 ${pnl:+,.2f}")
        
        position_str = "\n".join(position_lines) if position_lines else "  • 无持仓"
        
        # 风控信息
        blocker_str = ""
        if summary.risk_blockers:
            blocker_lines = [f"  • {b.get('reason', 'unknown')}" for b in summary.risk_blockers[:3]]
            blocker_str = f"\n⚠️ 风控拦截:\n" + "\n".join(blocker_lines)
        
        # 关注标的
        focus_str = ", ".join(summary.focus_symbols) if summary.focus_symbols else "暂无"
        
        report = f"""📊 收盘总结 {summary.date} {summary.market}

═══ 执行概况 ═══
• 信号: BUY {summary.signals['buy']} / EXIT {summary.signals['exit']} / HOLD {summary.signals['hold']}
• 订单: 成交 {summary.orders['filled']} / 待成交 {summary.orders['pending']}

═══ 账户状态 ═══
• 净值: ${net_liq:,.2f}
• 浮盈亏: ${unrealized_pnl:+,.2f}{pnl_pct}
• 现金: ${cash:,.2f}

═══ 持仓 ═══
{position_str}{blocker_str}

═══ 明日关注 ═══
{focus_str}"""
        
        return report
    
    def run(self, market: str = "US") -> dict[str, Any]:
        """运行收盘总结"""
        artifacts_dir = resolve_artifacts_root() / "closer"

        # 检查是否有交易数据（判断是否交易日）
        if not check_has_trading_data(self.client, market):
            result = {
                "status": "skipped",
                "reason": "今日无交易数据（可能休市）",
                "market": market,
                "date": datetime.now().strftime("%Y-%m-%d")
            }
            write_json(artifacts_dir / "summary_latest.json", result)
            append_jsonl(artifacts_dir / "summary_history.jsonl", result)
            return result
        
        summary = self.generate_summary(market)
        report = self.format_report(summary)
        result = {
            "status": "ok",
            "summary": summary.to_dict(),
            "report": report
        }
        write_json(artifacts_dir / "summary_latest.json", result)
        append_jsonl(artifacts_dir / "summary_history.jsonl", result)
        return result


def run_closer(market: str = "US", base_url: str = "http://host.docker.internal:8088") -> dict[str, Any]:
    """运行收盘总结"""
    closer = TigerCloser(base_url)
    return closer.run(market)


if __name__ == "__main__":
    import sys
    market = sys.argv[1] if len(sys.argv) > 1 else "US"
    result = run_closer(market)
    print(json.dumps(result, indent=2, ensure_ascii=False))
