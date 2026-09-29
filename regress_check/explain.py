"""Run the user's explain commands after a failure. They are config, not code."""

from __future__ import annotations

import shlex
import subprocess

TAIL_LINES = 40
TIMEOUT_SEC = 120


def run_explain(commands: tuple[str, ...], cwd: str) -> list[str]:
    """Return output lines: one header per command plus the output tail."""
    if not commands:
        return ["--- explain: no commands configured in [regress].explain ---"]
    out: list[str] = []
    for cmd in commands:
        try:
            argv = shlex.split(cmd)
            if not argv:
                raise ValueError("empty command")
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SEC,
                cwd=cwd,
            )
        except FileNotFoundError:
            out.append(f"--- explain: {cmd} (not run: executable not found) ---")
            continue
        except subprocess.TimeoutExpired:
            out.append(f"--- explain: {cmd} (not run: timed out after {TIMEOUT_SEC}s) ---")
            continue
        except (OSError, ValueError) as exc:
            out.append(f"--- explain: {cmd} (not run: {exc}) ---")
            continue
        out.append(f"--- explain: {cmd} (exit {proc.returncode}) ---")
        text = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        out.extend(text.splitlines()[-TAIL_LINES:])
    return out
