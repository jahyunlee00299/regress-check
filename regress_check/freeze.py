"""freeze: write actuals into the lock, with a reason, all-or-nothing."""

from __future__ import annotations

import datetime as dt

from regress_check.actuals import read_all
from regress_check.errors import CannotCheck
from regress_check.lock import read_lock, write_lock
from regress_check.registry import Registry


def freeze(registry: Registry, reason: str, only: list[str] | None = None) -> list[str]:
    """Update the lock. Returns one human line per changed golden."""
    reason = (reason or "").strip()
    if not reason:
        raise CannotCheck("freeze requires a non-empty --reason", rule="freeze")

    ids = list(only) if only else list(registry.goldens)
    unknown = [gid for gid in ids if gid not in registry.goldens]
    if unknown:
        raise CannotCheck(f"--only names goldens not in the registry: {', '.join(unknown)}", rule="freeze")

    values, errors = read_all(registry, ids)
    if errors:
        detail = "; ".join(exc.reason for exc in errors.values())
        raise CannotCheck(f"cannot freeze, lock not written: {detail}", rule="actual")

    lock = read_lock(registry.lock_path, missing_ok=True)
    goldens = lock["goldens"]
    today = dt.date.today().isoformat()
    changed: list[str] = []

    for gid in ids:
        g = registry.goldens[gid]
        new = values[gid]
        entry = goldens.get(gid)
        if entry is not None and (
            entry["expected"] == new and entry["rtol"] == g.rtol and entry["atol"] == g.atol
        ):
            continue
        old = entry["expected"] if entry else None
        history = entry["history"] if entry else []
        history.append(
            {"date": today, "reason": reason, "old": old, "new": new, "rtol": g.rtol, "atol": g.atol}
        )
        goldens[gid] = {"expected": new, "rtol": g.rtol, "atol": g.atol, "history": history}
        changed.append(f"{gid}: {old} -> {new} (rtol={g.rtol:g} atol={g.atol:g})")

    # A full freeze is the recorded decision to retire orphans; --only never is.
    if not only:
        retired = lock.setdefault("retired", [])
        for gid in [k for k in goldens if k not in registry.goldens]:
            entry = goldens.pop(gid)
            retired.append({"id": gid, "date": today, "reason": reason, "last_expected": entry["expected"], "history": entry["history"]})
            changed.append(f"{gid}: retired (no longer in registry)")

    if changed:
        write_lock(registry.lock_path, lock)
    return changed
