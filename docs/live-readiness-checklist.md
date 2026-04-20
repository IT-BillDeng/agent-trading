# Live Readiness Checklist

`live_trade` 只能在显式 checklist 通过后进入。

当前 canonical checklist id:

- `live-readiness-v1`

## Required Items

以下项目必须全部为 `true`:

- `p0_safety_tests_passed`
- `p1_risk_tests_passed`
- `paper_shadow_20d_stable`
- `fee_model_confidence_ok`
- `recent_data_health_ok`
- `broker_no_unknown_open_orders`
- `execution_state_reconciled`
- `operator_confirmed`

说明:

- `operator_confirmed` 由 API 请求中的 `confirm_live=true` 触发，不应依赖默认值。
- 其余字段由人工或上层审核流程显式提供，不允许缺省进入 `live_trade`。

## API Contract

进入 `live_trade` 时，`POST /api/trading/mode` 必须至少包含:

```json
{
  "mode": "live_trade",
  "confirm_live": true,
  "readiness_checklist_id": "live-readiness-v1",
  "checklist": {
    "p0_safety_tests_passed": true,
    "p1_risk_tests_passed": true,
    "paper_shadow_20d_stable": true,
    "fee_model_confidence_ok": true,
    "recent_data_health_ok": true,
    "broker_no_unknown_open_orders": true,
    "execution_state_reconciled": true
  }
}
```

如果:

- 缺少 `readiness_checklist_id`
- `confirm_live != true`
- checklist 任一必选项为 `false`

则 API 必须拒绝切换到 `live_trade`。

## Important Boundary

即使 `ControlPlane.global.mode = live_trade` 已设置成功，真实下单仍必须同时满足:

- `app.mode = live`
- `execution.submit_mode = live`
- `execution.live_submit = true`

也就是说，`live readiness checklist` 只允许进入 control plane 的 live 模式，
**不会绕过 `LiveExecutionAdapter` 的最终 live gate**。
