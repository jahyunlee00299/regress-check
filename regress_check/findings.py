"""Findings in the fiducial schema (rule/status/confidence/message/fix/action).

Same vocabulary as fiducial's signals.py so a caller can treat the four axes as
one family, but redefined here: this package never imports its siblings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1

ACTION = {
    "moved": (
        "Do not edit the expected value or the tolerance to make this pass. "
        "Find why the number moved (run with --explain); re-freeze with a "
        "reason only if the change is intended."
    ),
    "widened": (
        "A tolerance was loosened after the freeze. Restore it, or re-freeze "
        "with --reason stating why the wider tolerance is justified."
    ),
    "orphan": (
        "A frozen check has no registry entry. Restore the golden, or retire "
        "it with a full `freeze --reason` so the deletion is on record."
    ),
    "configure": (
        "The check could not run. Fix the registry, the lock or the results "
        "file -- this is not a clean result."
    ),
}


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str  # violation | cannot_check
    confidence: str  # certain | needs_review
    message: str
    path: str | None = None
    entry: str | None = None
    key: str | None = None
    fix: dict[str, Any] | None = None
    action: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "rule": self.rule,
            "status": self.status,
            "confidence": self.confidence,
            "message": self.message,
        }
        for name in ("path", "entry", "key"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.fix is not None:
            out["fix"] = self.fix
        if self.action:
            out["action"] = self.action
        return out


def fix(applicability: str, apply: str, edit: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"applicability": applicability, "apply": apply}
    if edit is not None:
        out["edit"] = edit
    return out
