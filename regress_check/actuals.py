"""Read the numbers the model already wrote."""

from __future__ import annotations

import json
import math
import tomllib
from pathlib import Path
from typing import Any

from regress_check.errors import CannotCheck
from regress_check.registry import Golden, Registry


class ActualReader:
    """Loads each results file once per run."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self._docs: dict[Path, Any] = {}

    def _load(self, rel: str, gid: str) -> Any:
        path = self.base / rel
        if path in self._docs:
            return self._docs[path]
        if not path.is_file():
            raise CannotCheck(f"golden '{gid}': results file missing: {rel}", rule="actual")
        suffix = path.suffix.lower()
        if suffix not in (".json", ".toml"):
            raise CannotCheck(
                f"golden '{gid}': unsupported results file type: {rel} (json or toml)",
                rule="actual",
            )
        try:
            text = path.read_text(encoding="utf-8")
            doc = json.loads(text) if suffix == ".json" else tomllib.loads(text)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise CannotCheck(
                f"golden '{gid}': results file unparseable: {rel} ({exc})", rule="actual"
            ) from exc
        self._docs[path] = doc
        return doc

    def read(self, golden: Golden) -> int | float:
        rel, _, dotted = golden.actual.rpartition(":")
        node = self._load(rel, golden.id)
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                node = node[int(part)]
            else:
                raise CannotCheck(
                    f"golden '{golden.id}': key '{dotted}' not found in {rel} "
                    f"(stopped at '{part}')",
                    rule="actual",
                )
        if isinstance(node, bool) or not isinstance(node, (int, float)):
            raise CannotCheck(
                f"golden '{golden.id}': {golden.actual} is {type(node).__name__}, "
                f"not a number",
                rule="actual",
            )
        if not math.isfinite(node):
            raise CannotCheck(
                f"golden '{golden.id}': {golden.actual} is not finite ({node})", rule="actual"
            )
        return node


def read_all(
    registry: Registry, ids: list[str] | None = None
) -> tuple[dict[str, int | float], dict[str, CannotCheck]]:
    """Return ({id: value}, {id: CannotCheck}) for the given goldens."""
    reader = ActualReader(registry.base)
    values: dict[str, int | float] = {}
    errors: dict[str, CannotCheck] = {}
    for gid in ids if ids is not None else list(registry.goldens):
        try:
            values[gid] = reader.read(registry.goldens[gid])
        except CannotCheck as exc:
            errors[gid] = exc
    return values, errors
