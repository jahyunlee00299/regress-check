"""Read regress.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from regress_check.errors import CannotCheck

DEFAULT_RTOL = 1e-6
DEFAULT_ATOL = 0.0
CRITICAL_TAGS = ("manuscript", "fit", "commit", "remote")
LOCK_NAME = "regress.lock.json"


@dataclass(frozen=True)
class Golden:
    id: str
    actual: str
    rtol: float
    atol: float
    critical: str | None = None


@dataclass(frozen=True)
class Registry:
    path: Path
    goldens: dict[str, Golden] = field(default_factory=dict)
    explain: tuple[str, ...] = ()

    @property
    def base(self) -> Path:
        return self.path.parent

    @property
    def lock_path(self) -> Path:
        return self.base / LOCK_NAME


def _tolerance(gid: str, table: dict, name: str, default: float) -> float:
    value = table.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CannotCheck(f"golden '{gid}': {name} must be a number, got {value!r}")
    if value != value or value < 0 or value == float("inf"):
        raise CannotCheck(f"golden '{gid}': {name} must be finite and >= 0, got {value!r}")
    return float(value)


def load_registry(path: Path) -> Registry:
    if not path.is_file():
        raise CannotCheck(f"registry not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotCheck(f"registry unparseable: {path} ({exc})") from exc

    section = data.get("regress", {})
    explain = section.get("explain", []) if isinstance(section, dict) else None
    if not isinstance(explain, list) or not all(isinstance(c, str) for c in explain):
        raise CannotCheck("[regress].explain must be a list of command strings")

    raw = data.get("golden", {})
    if not isinstance(raw, dict):
        raise CannotCheck("[golden] must be a table of [golden.<id>] tables")
    goldens: dict[str, Golden] = {}
    for gid, table in raw.items():
        if not isinstance(table, dict):
            raise CannotCheck(f"golden '{gid}' must be a table")
        actual = table.get("actual")
        if not isinstance(actual, str) or ":" not in actual:
            raise CannotCheck(
                f"golden '{gid}': actual must be '<file>:<dotted.key>', got {actual!r}"
            )
        critical = table.get("critical")
        if critical is not None and critical not in CRITICAL_TAGS:
            raise CannotCheck(
                f"golden '{gid}': critical must be one of {', '.join(CRITICAL_TAGS)}, "
                f"got {critical!r}"
            )
        goldens[gid] = Golden(
            id=gid,
            actual=actual,
            rtol=_tolerance(gid, table, "rtol", DEFAULT_RTOL),
            atol=_tolerance(gid, table, "atol", DEFAULT_ATOL),
            critical=critical,
        )
    if not goldens:
        raise CannotCheck(f"no goldens declared in {path} -- nothing to check")
    return Registry(path=path, goldens=goldens, explain=tuple(explain))
