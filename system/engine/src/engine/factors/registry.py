from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import FactorDefinition, validate_factor_registry


class FactorRegistryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FactorRegistry:
    schema_version: int
    defaults: dict[str, Any]
    factors: dict[str, FactorDefinition]
    config_hash: str
    path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def load_factor_registry(path: str | Path) -> FactorRegistry:
    registry_path = Path(path).resolve()
    payload = json.loads(registry_path.read_text())
    result = validate_factor_registry(payload)
    if not result["valid"]:
        raise FactorRegistryValidationError(
            f"invalid factor registry {registry_path}: " + "; ".join(result["errors"])
        )

    return FactorRegistry(
        schema_version=int(result["schema_version"]),
        defaults=copy.deepcopy(result["defaults"]),
        factors=dict(result["factors"]),
        config_hash=str(result["config_hash"]),
        path=registry_path,
        raw=copy.deepcopy(payload),
        warnings=tuple(result["warnings"]),
    )
