"""SignalArbiter - resolve multiple rule signals into one final action per symbol."""

from __future__ import annotations

from dataclasses import replace
from typing import Any


class SignalArbiter:
    """Resolve multiple rule signals for the same symbol into one final signal."""

    def choose(self, signals: list[Any]) -> Any | None:
        if not signals:
            return None

        candidates = list(signals)
        resolution = "priority"

        exits = [signal for signal in candidates if getattr(signal, "action", None) == "EXIT"]
        buys = [signal for signal in candidates if getattr(signal, "action", None) == "BUY"]
        holds = [signal for signal in candidates if getattr(signal, "action", None) == "HOLD"]

        if exits and buys:
            candidates = exits
            resolution = "exit_over_buy"
        elif exits and holds:
            candidates = exits
            resolution = "conservative"
        elif buys and holds:
            candidates = buys
            resolution = "conservative"

        selected = self._sort_candidates(candidates)[0]

        if resolution != "exit_over_buy":
            same_action = [signal for signal in candidates if getattr(signal, "action", None) == getattr(selected, "action", None)]
            if len(same_action) > 1:
                priorities = {self._priority(signal) for signal in same_action}
                scores = {self._score(signal) for signal in same_action}
                if len(priorities) > 1:
                    resolution = "priority"
                elif len(scores) > 1:
                    resolution = "score"

        suppressed = [
            getattr(signal, "rule_id", "unknown")
            for signal in signals
            if getattr(signal, "rule_id", None) != getattr(selected, "rule_id", None)
        ]
        diagnostics = dict(getattr(selected, "diagnostics", {}) or {})
        diagnostics["arbiter"] = {
            "selected_rule_id": getattr(selected, "rule_id", "unknown"),
            "suppressed": suppressed,
            "resolution": resolution,
        }
        source_rule_ids = []
        effective_hashes = []
        for signal in signals:
            rule_id = getattr(signal, "rule_id", None)
            if rule_id and rule_id not in source_rule_ids:
                source_rule_ids.append(rule_id)
            effective_hash = getattr(signal, "effective_config_hash", None)
            if effective_hash and effective_hash not in effective_hashes:
                effective_hashes.append(effective_hash)
        return replace(
            selected,
            diagnostics=diagnostics,
            primary_rule_id=getattr(selected, "rule_id", None),
            source_rule_ids=source_rule_ids,
            effective_config_hashes=effective_hashes,
        )

    def _sort_candidates(self, signals: list[Any]) -> list[Any]:
        return sorted(
            signals,
            key=lambda signal: (
                self._action_rank(getattr(signal, "action", None)),
                self._priority(signal),
                -self._score(signal),
                str(getattr(signal, "rule_id", "")),
            ),
        )

    def _action_rank(self, action: str | None) -> int:
        order = {
            "EXIT": 0,
            "BUY": 1,
            "HOLD": 2,
        }
        return order.get(str(action), 99)

    def _priority(self, signal: Any) -> int:
        value = getattr(signal, "priority", None)
        try:
            return int(value)
        except Exception:
            return 999999

    def _score(self, signal: Any) -> float:
        value = getattr(signal, "score", 0)
        try:
            return float(value)
        except Exception:
            return 0.0
