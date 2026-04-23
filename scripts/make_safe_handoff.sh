#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOURCE_ROOT="${1:-${DEFAULT_SOURCE_ROOT}}"
OUTPUT_DIR="${2:-${SOURCE_ROOT}/handoff}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ZIP_PATH="${OUTPUT_DIR}/agent-trading-safe-handoff-${TIMESTAMP}.zip"

mkdir -p "${OUTPUT_DIR}"

export SOURCE_ROOT OUTPUT_DIR ZIP_PATH

python3 - <<'PY'
import fnmatch
import os
import zipfile
from pathlib import Path

source_root = Path(os.environ["SOURCE_ROOT"]).resolve()
zip_path = Path(os.environ["ZIP_PATH"]).resolve()

keep_specs = [
    "docs",
    "factors",
    "rules",
    "config/app.defaults.json",
    "config/app_config.docker.json",
    "config/*.example.json",
    "config/broker_fee.tiger.json",
    "agents",
    "cron",
    "scripts/make_safe_handoff.sh",
    "specs/factor-registry-schema-v1.md",
    "specs/strategist-output-schema-v1.md",
    "system/engine/requirements.txt",
    "system/engine/src",
    "system/engine/tests",
    "tests",
    "dashboard",
    "README.md",
    "docker-compose.yml",
]

exclude_patterns = [
    ".env",
    ".env.*",
    "properties/*",
    "runtime/*",
    "logs/latest/*",
    "logs/latest/execution_state.json",
    "logs/latest/control_state.json",
    "artifacts/broker/*",
    "*.pem",
    "*.key",
    "*token*",
    "*secret*",
    "__pycache__/",
    "*.pyc",
]


def is_excluded(rel_path: Path) -> bool:
    rel_posix = rel_path.as_posix()
    if "__pycache__" in rel_path.parts:
        return True
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(rel_posix, pattern):
            return True
        if fnmatch.fnmatch(rel_path.name, pattern):
            return True
    return False


def iter_matches(spec: str):
    if any(ch in spec for ch in "*?[]"):
        yield from source_root.glob(spec)
        return
    candidate = source_root / spec
    if candidate.exists():
        yield candidate


added = set()
zip_path.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for spec in keep_specs:
        for match in iter_matches(spec):
            if match.is_dir():
                for child in match.rglob("*"):
                    if child.is_dir():
                        continue
                    rel = child.relative_to(source_root)
                    rel_posix = rel.as_posix()
                    if rel_posix in added or is_excluded(rel):
                        continue
                    zf.write(child, rel_posix)
                    added.add(rel_posix)
            else:
                rel = match.relative_to(source_root)
                rel_posix = rel.as_posix()
                if rel_posix in added or is_excluded(rel):
                    continue
                zf.write(match, rel_posix)
                added.add(rel_posix)

required_exact = {
    "factors/registry.json",
    "specs/factor-registry-schema-v1.md",
    "README.md",
    "docker-compose.yml",
}
required_prefixes = {
    "factors/",
    "tests/",
}
protected_prefixes = (
    ".env",
    "properties/",
    "runtime/",
    "logs/latest/",
    "artifacts/broker/",
)

missing_exact = sorted(path for path in required_exact if path not in added)
missing_prefixes = sorted(
    prefix for prefix in required_prefixes if not any(path.startswith(prefix) for path in added)
)
protected_hits = sorted(
    path for path in added
    if path == ".env" or any(path.startswith(prefix) for prefix in protected_prefixes[1:])
)
if missing_exact or missing_prefixes or protected_hits:
    raise SystemExit(
        "safe handoff verification failed: "
        f"missing_exact={missing_exact!r} "
        f"missing_prefixes={missing_prefixes!r} "
        f"protected_hits={protected_hits!r}"
    )

print(f"packed_files={len(added)}")
PY

cat <<EOF
Safe handoff zip: ${ZIP_PATH}
Critical review files retained:
- factors/
- factors/registry.json
- specs/factor-registry-schema-v1.md
- tests/
- README.md
- docker-compose.yml
- scripts/make_safe_handoff.sh
- system/engine/requirements.txt
- config/broker_fee.tiger.json
- specs/strategist-output-schema-v1.md
Exclude rules:
- .env
- .env.*
- properties/*
- runtime/*
- logs/latest/*
- logs/latest/execution_state.json
- logs/latest/control_state.json
- artifacts/broker/*
- *.pem
- *.key
- *token*
- *secret*
- __pycache__/
- *.pyc
EOF
