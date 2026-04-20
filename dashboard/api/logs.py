from __future__ import annotations

import json
import sys
from datetime import datetime

from fastapi.responses import JSONResponse


_dashboard_main_module = None


def set_dashboard_main_module(module) -> None:
    global _dashboard_main_module
    _dashboard_main_module = module


def _dashboard_main():
    if _dashboard_main_module is not None:
        return _dashboard_main_module
    module = sys.modules.get("dashboard.main")
    if module is not None:
        return module
    from dashboard import main as dashboard_main
    return dashboard_main


async def api_audit(limit: int = 50):
    dashboard_main = _dashboard_main()

    result = []
    for log_dir in (dashboard_main.AUDIT_LOG_DIR, dashboard_main.LEGACY_LOG_DIR):
        if result or not log_dir.exists():
            continue
        for log_file in sorted(log_dir.glob("*.jsonl"), reverse=True):
            try:
                lines = log_file.read_text().strip().split("\n")
                for line in lines[-limit:]:
                    if line.strip():
                        entry = json.loads(line)
                        entry["_source"] = log_file.name
                        result.append(entry)
            except Exception:
                continue
            if len(result) >= limit:
                break
    return {"entries": result[:limit], "count": len(result)}


async def api_logs(log_name: str = "execution", lines: int = 100):
    dashboard_main = _dashboard_main()

    resolved = dashboard_main._resolve_log_file(log_name)
    if not resolved:
        available = [path.stem for _, path in dashboard_main._iter_log_files()]
        return JSONResponse({"error": f"log not found: {log_name}", "available": available}, status_code=404)
    section, log_file = resolved
    try:
        all_lines = log_file.read_text().strip().split("\n")
        entries = []
        for line in all_lines[-lines:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"_raw": line})
        return {
            "log": log_name,
            "section": section,
            "total_lines": len(all_lines),
            "returned": len(entries),
            "entries": entries,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_logs_overview():
    dashboard_main = _dashboard_main()

    try:
        return dashboard_main._build_logs_overview()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_logs_list():
    dashboard_main = _dashboard_main()

    logs = []
    for section, file_path in dashboard_main._iter_log_files():
        stat = file_path.stat()
        logs.append(
            {
                "name": file_path.stem,
                "section": section,
                "path": str(file_path),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "lines": sum(1 for _ in open(file_path)) if stat.st_size < 1_000_000 else None,
            }
        )
    return {"logs": logs}


def register_logs_routes(app) -> None:
    app.get("/api/audit")(api_audit)
    app.get("/api/logs")(api_logs)
    app.get("/api/logs/{log_name}")(api_logs)
    app.get("/api/logs-overview")(api_logs_overview)
    app.get("/api/logs-list")(api_logs_list)
