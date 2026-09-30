"""Command line: freeze / check / history. Exit 0 clean, 1 violations, 2 cannot check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from regress_check import __version__
from regress_check.errors import CannotCheck
from regress_check.explain import run_explain
from regress_check.findings import SCHEMA_VERSION, Finding
from regress_check.freeze import freeze
from regress_check.lock import read_lock
from regress_check.registry import Registry, load_registry
from regress_check.rules import check

DEFAULT_REGISTRY = "regress.toml"


def _cannot(reason: str) -> int:
    print(f"regress-check: cannot check — {reason}", file=sys.stderr)
    return 2


def _summary(findings: list[Finding], checked: int) -> dict[str, int]:
    return {
        "checked": checked,
        "violations": sum(f.status == "violation" for f in findings),
        "cannot_check": sum(f.status == "cannot_check" for f in findings),
    }


def _emit_json(findings: list[Finding], checked: int, explain: list[str] | None) -> None:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "findings": [f.as_dict() for f in findings],
        "summary": _summary(findings, checked),
    }
    if explain is not None:
        doc["explain"] = explain
    print(json.dumps(doc, indent=2, ensure_ascii=False))


def _emit_text(findings: list[Finding], checked: int) -> None:
    for f in findings:
        if f.status == "cannot_check":
            print(f"regress-check: cannot check — {f.message}")
        else:
            print(f"[{f.rule}] ({f.confidence}) {f.message}")
    s = _summary(findings, checked)
    print(
        f"regress-check: {s['violations']} violation(s), {s['cannot_check']} cannot-check "
        f"across {checked} golden(s)"
    )


def cmd_check(args: argparse.Namespace) -> int:
    registry: Registry | None = None
    try:
        registry = load_registry(Path(args.registry))
        findings = check(registry)
    except CannotCheck as exc:
        if args.format == "json":
            finding = Finding(
                rule=exc.rule, status="cannot_check", confidence="certain", message=exc.reason
            )
            _emit_json([finding], len(registry.goldens) if registry else 0, None)
            return 2
        return _cannot(exc.reason)

    checked = len(registry.goldens)
    failed = bool(findings)
    explain_lines: list[str] | None = None
    if failed and args.explain:
        explain_lines = run_explain(registry.explain, str(registry.base))

    if args.format == "json":
        _emit_json(findings, checked, explain_lines)
    else:
        _emit_text(findings, checked)
        if explain_lines is not None:
            print("\n".join(explain_lines))
        elif failed:
            if registry.explain:
                print(f"hint: rerun with --explain to run: {', '.join(registry.explain)}")
            else:
                print("hint: no [regress].explain commands configured; add some to find the cause")

    if any(f.status == "violation" for f in findings):
        return 1
    return 2 if failed else 0


def cmd_freeze(args: argparse.Namespace) -> int:
    try:
        registry = load_registry(Path(args.registry))
        changed = freeze(registry, args.reason, args.only)
    except CannotCheck as exc:
        return _cannot(exc.reason)
    if not changed:
        print("regress-check: nothing changed; lock untouched")
    for line in changed:
        print(f"frozen {line}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    try:
        registry = load_registry(Path(args.registry))
        lock = read_lock(registry.lock_path)
        entries = lock["goldens"]
        if args.id is not None and args.id not in entries:
            raise CannotCheck(f"no frozen golden named '{args.id}'", rule="lock")
    except CannotCheck as exc:
        return _cannot(exc.reason)
    for gid in [args.id] if args.id else entries:
        entry = entries[gid]
        print(f"{gid}: expected {entry['expected']} (rtol={entry['rtol']:g} atol={entry['atol']:g})")
        for h in entry["history"]:
            print(
                f"  {h['date']}  {h['old']} -> {h['new']}  "
                f"rtol={h['rtol']:g} atol={h['atol']:g}  reason: {h['reason']}"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="regress-check",
        description="Does it come out the same way twice? Freeze critical numbers, fail when one moves.",
    )
    p.add_argument("--version", action="version", version=f"regress-check {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def registry_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("registry", nargs="?", default=DEFAULT_REGISTRY, help="path to regress.toml")

    f = sub.add_parser("freeze", help="record current actuals in the lock (reason required)")
    registry_arg(f)
    f.add_argument("--reason", default="", help="why these values are being frozen (required)")
    f.add_argument("--only", nargs="+", metavar="ID", help="freeze only these goldens")
    f.set_defaults(func=cmd_freeze)

    c = sub.add_parser("check", help="compare current actuals against the lock")
    registry_arg(c)
    c.add_argument("--format", choices=("text", "json"), default="text")
    c.add_argument("--explain", action="store_true", help="on failure, run [regress].explain commands")
    c.set_defaults(func=cmd_check)

    h = sub.add_parser("history", help="print freeze history")
    h.add_argument("id", nargs="?", help="golden id (default: all)")
    h.add_argument("--registry", default=DEFAULT_REGISTRY, help="path to regress.toml")
    h.set_defaults(func=cmd_history)
    return p


def _run(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


def main(argv: list[str] | None = None) -> int:
    rc = _run(argv)
    from . import __version__, _update_notice

    _update_notice.notify("regress-check", __version__)
    return rc
