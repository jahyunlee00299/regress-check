"""The rules. Each one is a comparison between registry, lock and results.

R1 moved              a value left its frozen tolerance band
R2 tolerance-widened  the registry tolerance is looser than the frozen one
R3 unfrozen           a golden has no lock entry (cannot check)
R4 lock-orphan        a lock entry has no golden (a deletion must be visible)

R1 is judged against the *tighter* of the registry and frozen tolerances, so
widening in the registry can never excuse a move by itself, while narrowing
takes effect immediately.
"""

from __future__ import annotations

from typing import Any

from regress_check.actuals import read_all
from regress_check.findings import ACTION, Finding, fix
from regress_check.lock import read_lock
from regress_check.registry import Golden, Registry


def num(value: float) -> str:
    return f"{value:.10g}"


def within(expected: float, actual: float, rtol: float, atol: float) -> bool:
    return abs(actual - expected) <= atol + rtol * abs(expected)


def _moved(g: Golden, entry: dict[str, Any], actual: float) -> Finding | None:
    expected = entry["expected"]
    rtol = min(g.rtol, entry["rtol"])
    atol = min(g.atol, entry["atol"])
    if within(expected, actual, rtol, atol):
        return None
    delta = actual - expected
    rel = f"{delta / abs(expected) * 100:+.4g}%" if expected != 0 else "n/a (expected is 0)"
    tag = g.critical or "untagged"
    return Finding(
        rule="moved",
        status="violation",
        confidence="certain",
        message=(
            f"{g.id} moved: expected {num(expected)}, actual {num(actual)} "
            f"(delta {delta:+.6g}, {rel}); tolerance rtol={num(rtol)} atol={num(atol)} "
            f"allows {num(atol + rtol * abs(expected))}; critical={tag}"
        ),
        path=g.actual,
        entry=g.id,
        fix=fix(
            "unsafe",
            "suggest_only",
            {"note": "re-freeze with a reason only if the change is intended"},
        ),
        action=ACTION["moved"],
    )


def _widened(g: Golden, entry: dict[str, Any]) -> Finding | None:
    changed = [
        f"{name} {num(frozen)} -> {num(now)}"
        for name, now, frozen in (("rtol", g.rtol, entry["rtol"]), ("atol", g.atol, entry["atol"]))
        if now > frozen
    ]
    if not changed:
        return None
    return Finding(
        rule="tolerance-widened",
        status="violation",
        confidence="certain",
        message=(
            f"{g.id}: tolerance widened after the freeze ({', '.join(changed)}); "
            f"a looser tolerance needs a re-freeze with a recorded reason"
        ),
        entry=g.id,
        fix=fix(
            "unsafe",
            "suggest_only",
            {"note": "restore the frozen tolerance, or re-freeze with --reason"},
        ),
        action=ACTION["widened"],
    )


def _cannot(rule: str, message: str, entry: str | None = None) -> Finding:
    return Finding(
        rule=rule,
        status="cannot_check",
        confidence="certain",
        message=message,
        entry=entry,
        action=ACTION["configure"],
    )


def check(registry: Registry) -> list[Finding]:
    lock = read_lock(registry.lock_path)
    frozen = lock["goldens"]
    values, errors = read_all(registry)
    findings: list[Finding] = []

    for gid, g in registry.goldens.items():
        entry = frozen.get(gid)
        if entry is None:
            findings.append(
                _cannot("unfrozen", f"{gid}: declared in the registry but never frozen -- run freeze", gid)
            )
            continue
        widened = _widened(g, entry)
        if widened:
            findings.append(widened)
        if gid in errors:
            findings.append(_cannot("actual", errors[gid].reason, gid))
            continue
        moved = _moved(g, entry, values[gid])
        if moved:
            findings.append(moved)

    for gid in frozen:
        if gid not in registry.goldens:
            findings.append(
                Finding(
                    rule="lock-orphan",
                    status="violation",
                    confidence="needs_review",
                    message=(
                        f"{gid}: frozen in {registry.lock_path.name} but no longer declared "
                        f"in the registry -- a deleted check should be a visible decision"
                    ),
                    entry=gid,
                    fix=fix("safe", "suggest_only", {"note": f"retire '{gid}' with a full freeze --reason"}),
                    action=ACTION["orphan"],
                )
            )
    return findings
