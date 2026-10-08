"""regress.lock.json: machine-written, committed, append-only history."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from regress_check.errors import CannotCheck

VERSION = 1


def empty_lock() -> dict[str, Any]:
    return {"version": VERSION, "goldens": {}}


def read_lock(path: Path, *, missing_ok: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if missing_ok:
            return empty_lock()
        raise CannotCheck(f"lock file missing: {path.name} -- run freeze first", rule="lock")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CannotCheck(f"lock unparseable: {path.name} ({exc})", rule="lock") from exc
    if (
        not isinstance(data, dict)
        or data.get("version") != VERSION
        or not isinstance(data.get("goldens"), dict)
    ):
        raise CannotCheck(f"lock has an unexpected shape: {path.name}", rule="lock")
    for gid, entry in data["goldens"].items():
        problem = _entry_problem(entry)
        if problem:
            raise CannotCheck(f"lock entry '{gid}' is malformed in {path.name}: {problem}", rule="lock")
    return data


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _entry_problem(entry: Any) -> str | None:
    """A hand-edited or truncated lock must read as 'cannot check' (exit 2), never as a traceback (exit 1)."""
    if not isinstance(entry, dict):
        return "not an object"
    for key in ("expected", "rtol", "atol"):
        if key not in entry:
            return f"missing '{key}'"
        if not _is_number(entry[key]):
            return f"'{key}' is not a number"
    if not isinstance(entry.get("history"), list):
        return "missing or non-list 'history'"
    return None


def write_lock(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
