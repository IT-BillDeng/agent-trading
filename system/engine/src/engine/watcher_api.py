"""Watcher API 版本 - 通过 Dashboard API 监控系统健康"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

from .artifacts import append_jsonl, resolve_artifacts_root, write_json


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
        except urllib.error.URLError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}
    
    def post(self, endpoint: str, data: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
        """POST 请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}


class TigerWatcherAPI:
    """Watcher API 版本"""
    
    def __init__(self, base_url: str = "http://host.docker.internal:8088", state_file: Path | None = None):
        self.client = DashboardAPIClient(base_url)
        self.state_file = state_file or self._default_state_file()
        self.state = self._load_state()

    def _default_state_file(self) -> Path:
        broker_path = Path("/tmp/broker_watcher_state.json")
        legacy_path = Path("/tmp/tiger_watcher_state.json")
        if broker_path.exists() or not legacy_path.exists():
            return broker_path
        return legacy_path
    
    def _load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {
            "last_check": None,
            "last_level": "info",
            "consecutive_errors": 0,
            "alert_cooldowns": {}
        }
    
    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2))

    @staticmethod
    def _normalize_lock_reason(reason: Any) -> str:
        return str(reason or "unknown").strip().lower()

    def _is_manual_lock_reason(self, reason: Any) -> bool:
        normalized = self._normalize_lock_reason(reason)
        return normalized == "manual_lock" or normalized.startswith("manual_lock")
    
    def check_health(self) -> HealthCheck:
        """检查基本健康状态"""
        data = self.client.get("/health")
        
        if "error" in data:
            return HealthCheck(
                name="health",
                status="error",
                message=f"API 不可达: {data['error']}"
            )
        
        if data.get("status") == "ok":
            return HealthCheck(
                name="health",
                status="ok",
                message="Dashboard API 正常"
            )
        
        return HealthCheck(
            name="health",
            status="warning",
            message="Dashboard API 响应异常",
            details=data
        )
    
    def check_engine_health(self) -> HealthCheck:
        """检查引擎健康状态（通过 /api/engine 的 cycle 数据判断）"""
        data = self.client.get("/api/engine")
        
        if "error" in data:
            return HealthCheck(
                name="engine_health",
                status="error",
                message=f"引擎健康检查失败: {data['error']}"
            )
        
        cycle = data.get("last_cycle")
        if not cycle:
            return HealthCheck(
                name="engine_health",
                status="warning",
                message="引擎无执行周期记录",
                details=data
            )
        
        cycle_id = cycle.get("cycle_id", "unknown")
        return HealthCheck(
            name="engine_health",
            status="ok",
            message=f"引擎健康 (cycle={cycle_id})",
            details={"cycle_id": cycle_id}
        )
    
    def check_engine_state(self) -> HealthCheck:
        """检查引擎控制状态"""
        data = self.client.get("/api/engine")
        
        if "error" in data:
            return HealthCheck(
                name="engine_state",
                status="error",
                message=f"获取引擎状态失败: {data['error']}"
            )
        
        control = data.get("control_state", {})
        locked = control.get("locked", False)
        mode = control.get("canonical_mode") or control.get("trading_mode", "off")
        
        if locked:
            reason = control.get("reason", "unknown")
            if self._is_manual_lock_reason(reason):
                return HealthCheck(
                    name="engine_state",
                    status="warning",
                    message=f"引擎处于人工锁定状态: {reason}",
                    details={
                        "locked": True,
                        "reason": reason,
                        "mode": mode,
                        "lock_kind": "manual",
                        "fault": False,
                    }
                )
            return HealthCheck(
                name="engine_state",
                status="error",
                message=f"引擎异常锁定: {reason}",
                details={
                    "locked": True,
                    "reason": reason,
                    "mode": mode,
                    "lock_kind": "abnormal",
                    "fault": True,
                }
            )
        
        return HealthCheck(
            name="engine_state",
            status="ok",
            message=f"引擎正常 (mode={mode})",
            details={"locked": False, "mode": mode}
        )
    
    def check_last_cycle(self) -> HealthCheck:
        """检查最近执行周期"""
        data = self.client.get("/api/engine")
        
        if "error" in data:
            return HealthCheck(
                name="last_cycle",
                status="error",
                message=f"获取执行周期失败: {data['error']}"
            )
        
        cycle = data.get("last_cycle")
        if not cycle:
            return HealthCheck(
                name="last_cycle",
                status="warning",
                message="无执行周期记录"
            )
        
        cycle_id = cycle.get("cycle_id", "unknown")
        signals = cycle.get("strategy", {}).get("signals", [])
        risk = cycle.get("risk", {})
        blockers = risk.get("preview_blockers", [])
        
        return HealthCheck(
            name="last_cycle",
            status="ok",
            message=f"最近周期: {cycle_id}",
            details={
                "cycle_id": cycle_id,
                "signals": len(signals),
                "blockers": len(blockers)
            }
        )
    
    def check_signals(self) -> HealthCheck:
        """检查信号状态"""
        data = self.client.get("/api/signals")
        
        if "error" in data:
            return HealthCheck(
                name="signals",
                status="error",
                message=f"获取信号失败: {data['error']}"
            )
        
        signals = data.get("signals", [])
        buy_signals = [s for s in signals if s.get("action") == "BUY"]
        exit_signals = [s for s in signals if s.get("action") == "EXIT"]
        
        return HealthCheck(
            name="signals",
            status="ok",
            message=f"信号: {len(buy_signals)} BUY, {len(exit_signals)} EXIT",
            details={"total": len(signals), "buy": len(buy_signals), "exit": len(exit_signals)}
        )
    
    def check_risk(self) -> HealthCheck:
        """检查风控状态"""
        data = self.client.get("/api/risk")
        
        if "error" in data:
            return HealthCheck(
                name="risk",
                status="error",
                message=f"获取风控状态失败: {data['error']}"
            )
        
        blockers = data.get("preview_blockers", [])
        allowed = data.get("allowed_count", 0)
        
        if blockers:
            return HealthCheck(
                name="risk",
                status="warning",
                message=f"风控阻塞: {len(blockers)} 项",
                details={"blockers": blockers[:3]}
            )
        
        return HealthCheck(
            name="risk",
            status="ok",
            message=f"风控正常 (通过: {allowed})"
        )
    
    def check_account(self) -> HealthCheck:
        """检查账户状态"""
        data = self.client.get("/api/account")
        
        if "error" in data:
            return HealthCheck(
                name="account",
                status="error",
                message=f"获取账户状态失败: {data['error']}"
            )
        
        # 检查是否有异常
        if "error" in data:
            return HealthCheck(
                name="account",
                status="error",
                message=f"账户异常: {data.get('error')}"
            )
        
        net_liquidation = data.get("net_liquidation") or data.get("total_equity")
        
        if net_liquidation is not None and net_liquidation <= 0:
            return HealthCheck(
                name="account",
                status="error",
                message="账户净值异常",
                details=data
            )
        
        return HealthCheck(
            name="account",
            status="ok",
            message="账户正常",
            details=data
        )
    
    def run_all_checks(self) -> WatcherReport:
        """执行所有检查"""
        checks = [
            self.check_health(),
            self.check_engine_health(),
            self.check_engine_state(),
            self.check_last_cycle(),
            self.check_signals(),
            self.check_risk(),
            self.check_account()
        ]
        
        # 确定整体级别
        alerts = []
        level = AlertLevel.INFO
        
        for check in checks:
            if check.status == "error":
                level = AlertLevel.CRITICAL
                alerts.append(Alert(
                    level=AlertLevel.CRITICAL,
                    source=check.name,
                    message=check.message,
                    timestamp=datetime.now().isoformat()
                ))
            elif check.status == "warning" and level == AlertLevel.INFO:
                level = AlertLevel.WARNING

        engine_state_check = next((check for check in checks if check.name == "engine_state"), None)
        engine_already_locked = bool((engine_state_check.details or {}).get("locked")) if engine_state_check else False
        
        # 检查连续错误次数
        if level == AlertLevel.CRITICAL:
            self.state["consecutive_errors"] = self.state.get("consecutive_errors", 0) + 1
        else:
            self.state["consecutive_errors"] = 0
        
        # 升级到 Emergency
        if self.state["consecutive_errors"] >= 5:
            level = AlertLevel.EMERGENCY
            alerts.append(Alert(
                level=AlertLevel.EMERGENCY,
                source="watcher",
                message=f"连续错误 {self.state['consecutive_errors']} 次，升级为 Emergency",
                timestamp=datetime.now().isoformat(),
                action_taken="引擎已锁定，无需重复锁定" if engine_already_locked else "建议自动锁定引擎",
            ))
        
        # 更新状态
        self.state["last_check"] = datetime.now().isoformat()
        self.state["last_level"] = level.value
        self._save_state()
        
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


def run_watcher_check(base_url: str = "http://host.docker.internal:8088") -> dict[str, Any]:
    """运行 watcher 检查"""
    watcher = TigerWatcherAPI(base_url)
    report = watcher.run_all_checks()
    record = report.to_dict()

    artifacts_dir = resolve_artifacts_root() / "watcher"
    write_json(artifacts_dir / "latest.json", record)
    append_jsonl(artifacts_dir / "history.jsonl", record)

    return record


if __name__ == "__main__":
    # 命令行执行
    report = run_watcher_check()
    print(json.dumps(report, indent=2, ensure_ascii=False))
