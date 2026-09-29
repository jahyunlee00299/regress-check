# regress-check

Freeze the critical numbers your model produced, and fail when one moves — or
when someone makes it stop failing by loosening the tolerance.

It does **not run your model**. It compares numbers your model already wrote to
a results file (`json` or `toml`) against a frozen copy, and tells you when they
differ by more than you said they may.

## The failure this exists for

A regression check goes red. The fastest way to green is not to find out why:
raise `rtol`, or re-record the expected value. Both are one-line edits, both
look like maintenance in a diff, and both turn the check into a decoration. An
agent optimising for "tests pass" takes that shortcut by default.

So `regress-check` makes the shortcut itself the violation:

- **Freezing or changing an expected value requires a reason**, stored in the
  lock file's history with the old value, the new value and the tolerances.
  `freeze` without `--reason` exits 2 and writes nothing.
- **Widening a tolerance without a re-freeze is a violation** (`tolerance-widened`).
  Narrowing is silent. A move is always judged against the *tighter* of the
  registry and the frozen tolerance, so widening cannot excuse a move.

## A worked example

`regress.toml`, next to the results file:

```toml
[regress]
explain = ["python stub_fiducial.py"]   # run only on failure, with --explain

[golden.mpsp]
actual = "out/results.json:economics.mpsp"   # <file>:<dotted.key>
rtol = 0.005
critical = "manuscript"

[golden.yield]
actual = "out/results.json:economics.yield"
rtol = 0.01
```

Real output from a run of this repository's code:

```
$ regress-check freeze --reason "initial freeze"
frozen mpsp: None -> 3.17 (rtol=0.005 atol=0)
frozen yield: None -> 0.91 (rtol=0.01 atol=0)
exit 0

$ regress-check check
regress-check: 0 violation(s), 0 cannot-check across 2 golden(s)
exit 0
```

The model is re-run and MPSP drifts from 3.17 to 3.27:

```
$ regress-check check --explain
[moved] (certain) mpsp moved: expected 3.17, actual 3.27 (delta +0.1, +3.155%); tolerance rtol=0.005 atol=0 allows 0.01585; critical=manuscript
regress-check: 1 violation(s), 0 cannot-check across 2 golden(s)
--- explain: python stub_fiducial.py (exit 0) ---
k_17 is 0.1077 in the model and 44.0 in three fixtures
exit 1
```

Then the shortcut — loosening `rtol` to 0.05 instead of finding `k_17`:

```
$ regress-check check
[tolerance-widened] (certain) mpsp: tolerance widened after the freeze (rtol 0.005 -> 0.05); a looser tolerance needs a re-freeze with a recorded reason
[moved] (certain) mpsp moved: expected 3.17, actual 3.27 (delta +0.1, +3.155%); tolerance rtol=0.005 atol=0 allows 0.01585; critical=manuscript
regress-check: 2 violation(s), 0 cannot-check across 2 golden(s)
hint: rerun with --explain to run: python stub_fiducial.py
exit 1

$ regress-check freeze --reason ""
regress-check: cannot check — freeze requires a non-empty --reason
exit 2
```

When the change is intended, say so, and it is on record:

```
$ regress-check freeze --reason "solver upgrade shifted MPSP; tolerance 5% agreed with PI"
frozen mpsp: 3.17 -> 3.27 (rtol=0.05 atol=0)

$ regress-check history mpsp
mpsp: expected 3.27 (rtol=0.05 atol=0)
  2026-09-30  None -> 3.17  rtol=0.005 atol=0  reason: initial freeze
  2026-09-30  3.17 -> 3.27  rtol=0.05 atol=0  reason: solver upgrade shifted MPSP; tolerance 5% agreed with PI
```

## Pointing at the cause

A regression diff on its own is a mystery: "MPSP moved 3.17%". `[regress].explain`
lists commands — yours to choose — that are run, on failure only, when you pass
`--explain`. Point them at the sibling axes and the mystery gets a cause:

```
regress-check:  "MPSP moved 3.17%"
fiducial check: "k_17 is 0.1077 in the model and 44.0 in three fixtures"
```

```toml
[regress]
explain = ["fiducial check", "provenance-check check provenance.toml"]
```

The example above uses a one-line stub in place of `fiducial`, so the
`k_17` line is scripted, not discovered — the point is the plumbing. Commands are
split with `shlex` and run with `shell=False`, 120 s timeout, from the registry's
directory; the last 40 lines of output are appended under a
`--- explain: <cmd> (exit N) ---` header. A missing executable is reported inline
and never fatal, and `regress-check` never imports the tools it calls.

## Exit codes

```
0   clean          it compared frozen numbers and every one held
1   violations     a number moved, a tolerance was widened, a check was orphaned
2   cannot check   registry missing/unparseable, zero goldens declared, lock missing,
                   a golden never frozen, a results file missing/unparseable,
                   a key path not found, a value that is not a number (bool included)
```

Violations win: a run with one moved number and one missing results file exits 1.
Exit 2 prints `regress-check: cannot check — <reason>` — a check that compared
nothing is never reported as clean.

## Rules

| rule | fires when | confidence | fix |
|---|---|---|---|
| `moved` | `|actual - expected| > atol + rtol * |expected|` | certain | unsafe / suggest_only |
| `tolerance-widened` | registry `rtol`/`atol` larger than the frozen one | certain | unsafe / suggest_only |
| `unfrozen` | golden in registry, absent from lock | cannot_check | — |
| `lock-orphan` | lock entry with no golden in the registry | needs_review | safe / suggest_only |

`--format json` emits findings in the same schema as `fiducial`
(`rule/status/confidence/message/fix/action`) plus `summary {checked, violations, cannot_check}`.

A full `freeze` (no `--only`) is the recorded decision to retire an orphan: it
moves the entry to `retired` in the lock with the reason. `--only` never retires.

## Install

Not yet published to PyPI — clone and `pip install .` into a venv, or run
`python -m regress_check` from a checkout. Standard library only, Python 3.11+.

## Commands

```
regress-check freeze [regress.toml] --reason "<text>" [--only ID ...]
regress-check check  [regress.toml] [--format text|json] [--explain]
regress-check history [ID] [--registry regress.toml]
```

Paths in the registry are relative to the registry file. The lock
(`regress.lock.json`) sits beside it and is committed; only `freeze` writes it,
all-or-nothing.

A pre-commit hook definition is in `.pre-commit-hooks.yaml`
(id `regress-check`, fires when `regress.toml` or `regress.lock.json` change).

## What it is not

It compares numbers; it does not snapshot whole files. For that,
[pytest-regressions](https://github.com/ESSS/pytest-regressions) and
[syrupy](https://github.com/syrupy-project/syrupy) are the right tools and this
does not replace them. It also cannot tell you whether a frozen number was
*right* — only that it did not change, and that changing it left a reason behind.

Part of a family of four checks with the same `0/1/2` contract; see
[fiducial's FOUR_AXES.md](https://github.com/jahyunlee00299/fiducial/blob/main/docs/FOUR_AXES.md).
This one is axis ④, results.
