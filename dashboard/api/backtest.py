from __future__ import annotations

import json
import sys
from pathlib import Path

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


def _clean_nan_values(obj):
    import math

    if isinstance(obj, dict):
        return {k: _clean_nan_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan_values(item) for item in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


async def api_backtest(body: dict):
    dashboard_main = _dashboard_main()

    backtest_src = str(Path(dashboard_main.__file__).parent.parent / "system" / "engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)

    from engine.backtest import BacktestConfig, run_backtest

    symbols = body.get("symbols", ["AAPL"])
    start_date = body.get("start_date", "2026-01-01")
    end_date = body.get("end_date", "2026-04-01")
    timeframe = body.get("timeframe", "30min")
    initial_capital = body.get("initial_capital", 100000.0)

    broker_platform = body.get("broker_platform") or dashboard_main._current_broker_platform()
    data_source = body.get("data_source") or broker_platform
    market = body.get("market", "US")

    config = BacktestConfig(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        initial_capital=initial_capital,
        data_source=data_source,
        broker_platform=broker_platform,
        market=market,
    )
    result = run_backtest(config, dashboard_main.RULES_FILE)
    return {"status": "ok", "result": _clean_nan_values(result.to_dict())}


async def api_backtest_batch(body: dict):
    dashboard_main = _dashboard_main()

    backtest_src = str(Path(dashboard_main.__file__).parent.parent / "system" / "engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)

    from engine.backtest import BacktestConfig, run_backtest

    symbols = body.get("symbols", ["AAPL"])
    start_date = body.get("start_date", "2026-01-07")
    end_date = body.get("end_date", "2026-04-07")
    timeframe = body.get("timeframe", "30min")
    broker_platform = body.get("broker_platform") or dashboard_main._current_broker_platform()
    data_source = body.get("data_source") or broker_platform
    market = body.get("market", "US")
    param_sets = body.get("param_sets", [])

    if not param_sets:
        return JSONResponse({"error": "param_sets is required"}, status_code=400)
    if len(param_sets) > 50:
        return JSONResponse({"error": "max 50 param_sets per batch"}, status_code=400)

    results = []
    for ps in param_sets:
        label = ps.get("label", f"set_{len(results)}")
        params = ps.get("params", {})
        try:
            rules_file = dashboard_main.RULES_FILE
            rules = json.loads(rules_file.read_text()) if rules_file.exists() else {"rules": []}
            if params:
                _apply_param_overrides(rules, params)
            tmp_rules = dashboard_main.RULES_DIR / f"_batch_{label}.json"
            tmp_rules.write_text(json.dumps(rules, indent=2, ensure_ascii=False))

            config = BacktestConfig(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                initial_capital=100000.0,
                data_source=data_source,
                broker_platform=broker_platform,
                market=market,
            )
            bt_result = run_backtest(config, tmp_rules)
            bt_dict = _clean_nan_values(bt_result.to_dict())
            results.append(
                {
                    "label": label,
                    "params": params,
                    "trades": bt_dict.get("total_trades", 0),
                    "return_pct": bt_dict.get("total_return_pct", 0),
                    "win_rate": bt_dict.get("win_rate", 0),
                    "sharpe": bt_dict.get("sharpe_ratio"),
                    "max_drawdown_pct": bt_dict.get("max_drawdown_pct"),
                    "winning_trades": bt_dict.get("winning_trades", 0),
                    "losing_trades": bt_dict.get("losing_trades", 0),
                    "commission_total": bt_dict.get("commission_total", 0),
                    "slippage_total": bt_dict.get("slippage_total", 0),
                    "transaction_cost_total": bt_dict.get("transaction_cost_total", 0),
                    "fee_drag_pct": bt_dict.get("fee_drag_pct", 0),
                }
            )
            tmp_rules.unlink(missing_ok=True)
        except Exception as e:
            results.append({"label": label, "params": params, "error": str(e)})

    valid = [r for r in results if "error" not in r and r.get("trades", 0) > 0]
    best = max(
        valid,
        key=lambda r: (
            r.get("return_pct", 0),
            r.get("sharpe") or float("-inf"),
            -(r.get("fee_drag_pct") or 0),
        ),
    ) if valid else None

    iterations_dir = dashboard_main.STRATEGIST_ITERATIONS_ARTIFACT_DIR
    legacy_iterations_dir = dashboard_main.RUNTIME_DIR / "strategist_iterations"
    iterations_dir.mkdir(parents=True, exist_ok=True)
    legacy_iterations_dir.mkdir(parents=True, exist_ok=True)
    dashboard_main.STRATEGIST_ITERATIONS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime as dt

    iter_id = f"iter_{dt.now().strftime('%Y%m%d_%H%M%S')}"
    iteration = {
        "iteration_id": iter_id,
        "timestamp": dt.now().isoformat(),
        "symbols": symbols,
        "period": f"{start_date} ~ {end_date}",
        "results": results,
        "best": best,
    }
    payload = json.dumps(iteration, indent=2, ensure_ascii=False)
    (iterations_dir / f"{iter_id}.json").write_text(payload)
    (iterations_dir / "latest.json").write_text(payload)
    (legacy_iterations_dir / f"{iter_id}.json").write_text(payload)
    (legacy_iterations_dir / "latest.json").write_text(payload)
    (dashboard_main.STRATEGIST_ITERATIONS_LOG_DIR / f"{iter_id}.json").write_text(payload)
    (dashboard_main.STRATEGIST_ITERATIONS_LOG_DIR / "latest.json").write_text(payload)
    return {"status": "ok", "iteration_id": iter_id, "results": results, "best": best}


def _apply_param_overrides(rules: dict, params: dict):
    param_map = {
        "trend_follow_enabled": ("trend_follow_30m", "enabled"),
        "rsi_enabled": ("rsi_reversal", "enabled"),
        "bollinger_enabled": ("bollinger_breakout", "enabled"),
        "sma_short": ("trend_follow_30m", "entry.conditions.items.0.params.period"),
        "sma_mid": ("trend_follow_30m", "entry.conditions.items.1.params.period"),
        "sma_long": ("trend_follow_30m", "entry.conditions.items.2.params.period"),
        "momentum_period": ("trend_follow_30m", "entry.conditions.items.3.params.period"),
        "momentum_threshold": ("trend_follow_30m", "entry.conditions.items.3.compare.value"),
        "bar_range_threshold": ("trend_follow_30m", "entry.conditions.items.4.compare.value"),
        "rsi_period": ("rsi_reversal", "entry.conditions.items.0.params.period"),
        "rsi_oversold": ("rsi_reversal", "entry.conditions.items.0.compare.value"),
        "rsi_overbought": ("rsi_reversal", "exit.conditions.items.0.compare.value"),
        "bb_period": ("bollinger_breakout", "entry.conditions.items.0.params.period"),
        "bb_std": ("bollinger_breakout", "entry.conditions.items.0.params.std_dev"),
        "volume_ratio": ("bollinger_breakout", "entry.conditions.items.1.ratio"),
        "rsi_sl": ("rsi_reversal", "exit.conditions.items.1.threshold_pct"),
        "bb_sl": ("bollinger_breakout", "exit.conditions.items.1.threshold_pct"),
    }

    rules_list = rules.get("rules", [])
    rules_by_id = {r.get("rule_id"): r for r in rules_list}
    for param_name, value in params.items():
        if param_name in param_map:
            rule_id, json_path = param_map[param_name]
        elif "." in param_name:
            rule_id, json_path = param_name.split(".", 1)
        else:
            continue

        rule = rules_by_id.get(rule_id)
        if not rule:
            continue

        path_keys = json_path.split(".")
        target = rule
        for key in path_keys[:-1]:
            if isinstance(target, dict):
                target = target.get(key)
            elif isinstance(target, list) and key.isdigit():
                idx = int(key)
                target = target[idx] if idx < len(target) else None
            else:
                target = None
                break
            if target is None:
                break

        last_key = path_keys[-1]
        if target is not None:
            if isinstance(target, dict):
                target[last_key] = value
            elif isinstance(target, list) and last_key.isdigit():
                idx = int(last_key)
                if idx < len(target):
                    target[idx] = value


async def api_backtest_results():
    dashboard_main = _dashboard_main()

    results_dir = dashboard_main.STRATEGIST_ITERATIONS_ARTIFACT_DIR
    legacy_results_dir = dashboard_main.RUNTIME_DIR / "backtest_results"
    if not results_dir.exists() and not legacy_results_dir.exists():
        return {"results": []}

    results = []
    candidate_files = []
    if results_dir.exists():
        candidate_files.extend(sorted(results_dir.glob("*.json"), reverse=True))
    if legacy_results_dir.exists():
        candidate_files.extend(sorted(legacy_results_dir.glob("*.json"), reverse=True))

    for result_file in candidate_files[:10]:
        try:
            content = json.loads(result_file.read_text())
            results.append(
                {
                    "filename": result_file.name,
                    "symbols": content.get("config", {}).get("symbols"),
                    "return_pct": content.get("total_return_pct"),
                    "total_trades": content.get("total_trades"),
                }
            )
        except Exception:
            continue
    return {"results": results}


async def api_rules_history():
    dashboard_main = _dashboard_main()

    backup_dir = dashboard_main.RULES_DIR / "rules_backup"
    if not backup_dir.exists():
        return {"history": []}

    history = []
    for backup_file in sorted(backup_dir.glob("rules_*.json"), reverse=True)[:10]:
        try:
            content = json.loads(backup_file.read_text())
            history.append(
                {
                    "filename": backup_file.name,
                    "updated_at": content.get("updated_at"),
                    "rule_count": len(content.get("rules", [])),
                }
            )
        except Exception:
            continue
    return {"history": history}


def register_backtest_routes(app) -> None:
    app.post("/api/backtest")(api_backtest)
    app.post("/api/backtest/batch")(api_backtest_batch)
    app.get("/api/backtest/results")(api_backtest_results)
    app.get("/api/rules/history")(api_rules_history)
