"""The one exception that means exit 2."""

from __future__ import annotations


class CannotCheck(Exception):
    """The tool could not compare anything. Never a clean result."""

    def __init__(self, reason: str, rule: str = "registry") -> None:
        super().__init__(reason)
        self.reason = reason
        self.rule = rule
