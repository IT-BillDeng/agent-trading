#!/usr/bin/env python3
"""Watcher - 执行健康检查并输出 JSON 报告"""

import json
import sys
import os
from pathlib import Path

# 添加源码路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from engine.watcher import TigerWatcher as BrokerWatcher, AlertLevel


def main():
    # 从环境变量获取路径
    runtime_dir = os.environ.get("ENGINE_RUNTIME_DIR", os.environ.get("TIGER_RUNTIME_DIR", "/app/runtime"))
    config_dir = os.environ.get("ENGINE_CONFIG_DIR", os.environ.get("TIGER_CONFIG_DIR", "/app/config"))
    
    # 运行检查
    watcher = BrokerWatcher(runtime_dir, config_dir)
    report = watcher.run_all_checks()
    
    # 输出 JSON 报告
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    
    # 返回退出码
    if report.level == AlertLevel.EMERGENCY:
        sys.exit(2)
    elif report.level in (AlertLevel.CRITICAL, AlertLevel.WARNING):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
