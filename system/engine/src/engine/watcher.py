"""Tiger Watcher - 系统健康监护人"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class HealthCheck:
    """单项健康检查结果"""
    name: str
    status: str  # ok / warning / error
    message: str
    details: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Alert:
    """告警记录"""
    level: AlertLevel
    source: str
    message: str
    timestamp: str
    action_taken: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WatcherReport:
    """Watcher 检查报告"""
    timestamp: str
    level: AlertLevel
    checks: list[HealthCheck]
    alerts: list[Alert]
    summary: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "checks": [c.to_dict() for c in self.checks],
            "alerts": [a.to_dict() for a in self.alerts],
            "summary": self.summary
        }


def _logs_root(runtime_dir: str | Path) -> Path:
    env_logs_dir = os.environ.get("ENGINE_LOGS_DIR") or os.environ.get("TIGER_LOGS_DIR")
    if env_logs_dir:
        return Path(env_logs_dir)

    runtime_path = Path(runtime_dir).resolve()
    if runtime_path.name == "engine" and len(runtime_path.parents) >= 2:
        return runtime_path.parents[1] / "logs"
    return runtime_path.parent / "logs"


def _service_log_dir(runtime_dir: str | Path) -> Path:
    return _logs_root(runtime_dir) / "service"


class WatcherState:
    """Watcher 状态管理"""
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = self._load()
    
    def _load(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {
            "last_check": None,
            "last_level": "info",
            "consecutive_warnings": 0,
            "consecutive_errors": 0,
            "alert_cooldowns": {},  # {alert_key: last_alert_time}
            "history": []  # 最近 N 次检查记录
        }
    
    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
    
    def update(self, level: AlertLevel):
        now = datetime.now().isoformat()
        
        # 更新连续计数
        if level in (AlertLevel.WARNING, AlertLevel.CRITICAL, AlertLevel.EMERGENCY):
            self.state["consecutive_errors"] += 1
            self.state["consecutive_warnings"] = 0
        elif level == AlertLevel.WARNING:
            self.state["consecutive_warnings"] += 1
            self.state["consecutive_errors"] = 0
        else:
            self.state["consecutive_warnings"] = 0
            self.state["consecutive_errors"] = 0
        
        self.state["last_check"] = now
        self.state["last_level"] = level.value
        
        # 保留最近 100 条历史
        self.state["history"].append({"time": now, "level": level.value})
        if len(self.state["history"]) > 100:
            self.state["history"] = self.state["history"][-100:]
    
    def should_alert(self, alert_key: str, cooldown_minutes: int = 30) -> bool:
        """检查是否应该发送告警（冷却期内不重复）"""
        cooldowns = self.state.get("alert_cooldowns", {})
        last_alert = cooldowns.get(alert_key)
        
        if not last_alert:
            return True
        
        try:
            last_time = datetime.fromisoformat(last_alert)
            return datetime.now() - last_time > timedelta(minutes=cooldown_minutes)
        except Exception:
            return True
    
    def mark_alert_sent(self, alert_key: str):
        """标记告警已发送"""
        if "alert_cooldowns" not in self.state:
            self.state["alert_cooldowns"] = {}
        self.state["alert_cooldowns"][alert_key] = datetime.now().isoformat()
    
    @property
    def consecutive_errors(self) -> int:
        return self.state.get("consecutive_errors", 0)
    
    @property
    def last_level(self) -> str:
        return self.state.get("last_level", "info")


class TigerWatcher:
    """Tiger 系统健康监护人"""
    
    def __init__(self, runtime_dir: str | Path, config_dir: str | Path):
        self.runtime_dir = Path(runtime_dir)
        self.config_dir = Path(config_dir)
        self.service_log_dir = _service_log_dir(self.runtime_dir)
        self.state_file = self.runtime_dir / "state" / "watcher_state.json"
        self.state = WatcherState(self.state_file)
        
        # 确保目录存在
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / "state").mkdir(exist_ok=True)
        (self.runtime_dir / "logs").mkdir(exist_ok=True)
        self.service_log_dir.mkdir(parents=True, exist_ok=True)
    
    def check_engine_health(self) -> HealthCheck:
        """检查引擎健康状态"""
        state_file = self.runtime_dir / "state" / "control_state.json"
        
        if not state_file.exists():
            return HealthCheck(
                name="engine_health",
                status="warning",
                message="控制状态文件不存在"
            )
        
        try:
            state = json.loads(state_file.read_text())
            locked = state.get("locked", False)
            mode = state.get("trading_mode", "off")
            
            if locked:
                reason = state.get("reason", "unknown")
                return HealthCheck(
                    name="engine_health",
                    status="error",
                    message=f"引擎已锁定: {reason}",
                    details={"locked": True, "reason": reason, "mode": mode}
                )
            
            return HealthCheck(
                name="engine_health",
                status="ok",
                message=f"引擎正常 (mode={mode})",
                details={"locked": False, "mode": mode}
            )
        
        except Exception as e:
            return HealthCheck(
                name="engine_health",
                status="error",
                message=f"读取控制状态失败: {e}"
            )
    
    def check_last_cycle(self) -> HealthCheck:
        """检查最近一次执行周期"""
        cycle_file = self.runtime_dir / ".last_execution_cycle.json"
        
        if not cycle_file.exists():
            return HealthCheck(
                name="last_cycle",
                status="warning",
                message="无执行周期记录"
            )
        
        try:
            cycle = json.loads(cycle_file.read_text())
            cycle_id = cycle.get("cycle_id", "unknown")
            
            # 检查信号
            signals = cycle.get("strategy", {}).get("signals", [])
            buy_signals = [s for s in signals if s.get("action") == "BUY"]
            exit_signals = [s for s in signals if s.get("action") == "EXIT"]
            
            # 检查风控
            risk = cycle.get("risk", {})
            blockers = risk.get("preview_blockers", [])
            
            return HealthCheck(
                name="last_cycle",
                status="ok",
                message=f"最近周期: {cycle_id}",
                details={
                    "cycle_id": cycle_id,
                    "total_signals": len(signals),
                    "buy_signals": len(buy_signals),
                    "exit_signals": len(exit_signals),
                    "risk_blockers": len(blockers)
                }
            )
        
        except Exception as e:
            return HealthCheck(
                name="last_cycle",
                status="error",
                message=f"读取执行周期失败: {e}"
            )
    
    def check_data_provider(self) -> HealthCheck:
        """检查数据源状态"""
        # 检查 app_config 中的数据源配置
        config_file = self.config_dir / "app_config.docker.json"
        
        if not config_file.exists():
            return HealthCheck(
                name="data_provider",
                status="warning",
                message="配置文件不存在"
            )
        
        try:
            config = json.loads(config_file.read_text())
            provider = config.get("strategy", {}).get("signal", {}).get("provider", "unknown")
            
            return HealthCheck(
                name="data_provider",
                status="ok",
                message=f"数据源: {provider}",
                details={"provider": provider}
            )
        
        except Exception as e:
            return HealthCheck(
                name="data_provider",
                status="error",
                message=f"读取配置失败: {e}"
            )
    
    def check_account_health(self) -> HealthCheck:
        """检查账户状态（从最近周期获取）"""
        cycle_file = self.runtime_dir / ".last_execution_cycle.json"
        
        if not cycle_file.exists():
            return HealthCheck(
                name="account_health",
                status="warning",
                message="无账户数据"
            )
        
        try:
            cycle = json.loads(cycle_file.read_text())
            asset_snapshot = cycle.get("asset_snapshot")
            
            if not asset_snapshot:
                return HealthCheck(
                    name="account_health",
                    status="warning",
                    message="无资产快照"
                )
            
            net_liquidation = asset_snapshot.get("netLiquidation", 0)
            buying_power = asset_snapshot.get("buyingPower", 0)
            
            # 检查异常
            if net_liquidation <= 0:
                return HealthCheck(
                    name="account_health",
                    status="error",
                    message="账户净值异常",
                    details=asset_snapshot
                )
            
            return HealthCheck(
                name="account_health",
                status="ok",
                message=f"净值: ${net_liquidation:,.2f}",
                details=asset_snapshot
            )
        
        except Exception as e:
            return HealthCheck(
                name="account_health",
                status="error",
                message=f"读取账户数据失败: {e}"
            )
    
    def check_risk_status(self) -> HealthCheck:
        """检查风控状态"""
        cycle_file = self.runtime_dir / ".last_execution_cycle.json"
        
        if not cycle_file.exists():
            return HealthCheck(
                name="risk_status",
                status="ok",
                message="无风控数据（正常）"
            )
        
        try:
            cycle = json.loads(cycle_file.read_text())
            risk = cycle.get("risk", {})
            blockers = risk.get("preview_blockers", [])
            
            if blockers:
                blocker_msgs = [b.get("reason", "") for b in blockers[:3]]
                return HealthCheck(
                    name="risk_status",
                    status="warning",
                    message=f"风控阻塞: {len(blockers)} 项",
                    details={"blockers": blocker_msgs}
                )
            
            return HealthCheck(
                name="risk_status",
                status="ok",
                message="风控正常"
            )
        
        except Exception as e:
            return HealthCheck(
                name="risk_status",
                status="error",
                message=f"读取风控数据失败: {e}"
            )
    
    def run_all_checks(self) -> WatcherReport:
        """执行所有检查"""
        checks = [
            self.check_engine_health(),
            self.check_last_cycle(),
            self.check_data_provider(),
            self.check_account_health(),
            self.check_risk_status()
        ]
        
        # 确定整体级别
        alerts = []
        level = AlertLevel.INFO
        
        for check in checks:
            if check.status == "error":
                level = max(level, AlertLevel.CRITICAL, key=lambda x: ["info", "warning", "critical", "emergency"].index(x.value))
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    source=check.name,
                    message=check.message,
                    timestamp=datetime.now().isoformat()
                ))
            elif check.status == "warning":
                level = max(level, AlertLevel.WARNING, key=lambda x: ["info", "warning", "critical", "emergency"].index(x.value))
        
        # 检查连续错误次数，决定是否升级到 Emergency
        if self.state.consecutive_errors >= 5:
            level = AlertLevel.EMERGENCY
            alerts.append(Alert(
                level=AlertLevel.EMERGENCY,
                source="watcher",
                message=f"连续错误 {self.state.consecutive_errors} 次，升级为 Emergency",
                timestamp=datetime.now().isoformat()
            ))
        
        # 更新状态
        self.state.update(level)
        self.state.save()
        
        # 生成报告
        summary = f"检查完成: {len(checks)} 项, 级别: {level.value}"
        if alerts:
            summary += f", 告警: {len(alerts)} 条"
        
        return WatcherReport(
            timestamp=datetime.now().isoformat(),
            level=level,
            checks=checks,
            alerts=alerts,
            summary=summary
        )


def run_watcher_check(runtime_dir: str | Path, config_dir: str | Path) -> dict[str, Any]:
    """运行 watcher 检查并返回报告"""
    watcher = TigerWatcher(runtime_dir, config_dir)
    report = watcher.run_all_checks()

    record = report.to_dict()
    record["source"] = "watcher"
    record["kind"] = "health_check"

    # 新目录：根目录 logs/service/watcher.jsonl
    service_log_file = watcher.service_log_dir / "watcher.jsonl"
    with service_log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 旧目录：runtime/.../logs/watcher_YYYYMMDD.jsonl，保留兼容
    legacy_log_dir = Path(runtime_dir) / "logs"
    legacy_log_file = legacy_log_dir / f"watcher_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with legacy_log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record
