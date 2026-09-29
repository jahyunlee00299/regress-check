"""Prove/refute tests. All on tmp_path, no network."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from regress_check.cli import main


def write_results(tmp: Path, **values) -> None:
    (tmp / "out").mkdir(exist_ok=True)
    (tmp / "out" / "results.json").write_text(json.dumps(values), encoding="utf-8")


def write_registry(tmp: Path, goldens: dict[str, dict] | None = None, explain=None) -> Path:
    goldens = goldens if goldens is not None else {"mpsp": {"actual": "out/results.json:mpsp", "rtol": 0.01}}
    lines = []
    if explain is not None:
        lines += ["[regress]", "explain = " + json.dumps(explain), ""]
    for gid, table in goldens.items():
        lines.append(f"[golden.{gid}]")
        for key, value in table.items():
            lines.append(f"{key} = {json.dumps(value)}")
        lines.append("")
    path = tmp / "regress.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run(*argv: str) -> int:
    return main(list(argv))


def freeze(reg: Path, reason: str = "initial freeze", *extra: str) -> int:
    return run("freeze", str(reg), "--reason", reason, *extra)


def lock_of(tmp: Path) -> dict:
    return json.loads((tmp / "regress.lock.json").read_text(encoding="utf-8"))


@pytest.fixture
def proj(tmp_path):
    write_results(tmp_path, mpsp=100.0)
    reg = write_registry(tmp_path)
    return tmp_path, reg


def test_freeze_then_check_clean(proj, capsys):
    tmp, reg = proj
    assert freeze(reg) == 0
    assert run("check", str(reg)) == 0
    assert "0 violation(s), 0 cannot-check across 1 golden(s)" in capsys.readouterr().out


def test_moved_beyond_rtol_fails(proj, capsys):
    tmp, reg = proj
    freeze(reg)
    write_results(tmp, mpsp=102.0)
    assert run("check", str(reg)) == 1
    out = capsys.readouterr().out
    assert "mpsp moved" in out and "expected 100" in out and "actual 102" in out


def test_exact_boundary_passes_and_epsilon_beyond_fails(proj):
    tmp, reg = proj
    freeze(reg)
    write_results(tmp, mpsp=101.0)  # |1.0| <= 0.01 * 100.0 exactly
    assert run("check", str(reg)) == 0
    write_results(tmp, mpsp=101.0001)
    assert run("check", str(reg)) == 1


def test_atol_contributes_to_band(tmp_path):
    write_results(tmp_path, x=2.0)
    reg = write_registry(tmp_path, {"x": {"actual": "out/results.json:x", "rtol": 0.0, "atol": 0.5}})
    freeze(reg)
    write_results(tmp_path, x=2.5)
    assert run("check", str(reg)) == 0
    write_results(tmp_path, x=2.6)
    assert run("check", str(reg)) == 1


def test_widened_rtol_fails_even_if_value_moved_within_new_band(proj, capsys):
    tmp, reg = proj
    freeze(reg)
    write_results(tmp, mpsp=102.0)
    write_registry(tmp, {"mpsp": {"actual": "out/results.json:mpsp", "rtol": 0.05}})
    assert run("check", str(reg)) == 1
    out = capsys.readouterr().out
    assert "[tolerance-widened]" in out
    assert "mpsp moved" in out  # widening does not excuse the move


def test_widened_rtol_alone_fails_with_value_unchanged(proj, capsys):
    tmp, reg = proj
    freeze(reg)
    write_registry(tmp, {"mpsp": {"actual": "out/results.json:mpsp", "rtol": 0.05}})
    assert run("check", str(reg)) == 1
    assert "tolerance widened" in capsys.readouterr().out


def test_widened_atol_fails(proj):
    tmp, reg = proj
    freeze(reg)
    write_registry(tmp, {"mpsp": {"actual": "out/results.json:mpsp", "rtol": 0.01, "atol": 0.1}})
    assert run("check", str(reg)) == 1


def test_narrowed_rtol_passes_and_applies(proj):
    tmp, reg = proj
    freeze(reg)
    write_registry(tmp, {"mpsp": {"actual": "out/results.json:mpsp", "rtol": 0.001}})
    assert run("check", str(reg)) == 0
    write_results(tmp, mpsp=100.5)  # inside frozen 1%, outside narrowed 0.1%
    assert run("check", str(reg)) == 1


def test_refreeze_with_reason_accepts_wider_tolerance(proj):
    tmp, reg = proj
    freeze(reg)
    write_registry(tmp, {"mpsp": {"actual": "out/results.json:mpsp", "rtol": 0.05}})
    assert freeze(reg, "solver tolerance is 5% by design") == 0
    assert run("check", str(reg)) == 0
    history = lock_of(tmp)["goldens"]["mpsp"]["history"]
    assert history[-1]["rtol"] == 0.05 and history[-1]["reason"].startswith("solver")


@pytest.mark.parametrize("reason", ["", "   ", "\t\n"])
def test_freeze_without_reason_is_exit_2(proj, reason, capsys):
    tmp, reg = proj
    assert freeze(reg, reason) == 2
    assert "cannot check" in capsys.readouterr().err
    assert not (tmp / "regress.lock.json").exists()


def test_freeze_missing_reason_flag_is_exit_2(proj):
    tmp, reg = proj
    assert run("freeze", str(reg)) == 2
    assert not (tmp / "regress.lock.json").exists()


def test_freeze_over_unreadable_actual_writes_no_lock(tmp_path):
    write_results(tmp_path, a=1.0)
    reg = write_registry(
        tmp_path,
        {"a": {"actual": "out/results.json:a"}, "b": {"actual": "out/results.json:missing"}},
    )
    assert freeze(reg) == 2
    assert not (tmp_path / "regress.lock.json").exists()


def test_freeze_failure_leaves_existing_lock_untouched(tmp_path):
    write_results(tmp_path, a=1.0, b=2.0)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}, "b": {"actual": "out/results.json:b"}})
    freeze(reg)
    before = (tmp_path / "regress.lock.json").read_text(encoding="utf-8")
    write_results(tmp_path, a=5.0)  # b vanishes
    assert freeze(reg, "try again") == 2
    assert (tmp_path / "regress.lock.json").read_text(encoding="utf-8") == before


def test_zero_goldens_is_exit_2(tmp_path, capsys):
    reg = tmp_path / "regress.toml"
    reg.write_text("[regress]\nexplain = []\n", encoding="utf-8")
    assert run("check", str(reg)) == 2
    assert "no goldens" in capsys.readouterr().err


def test_missing_registry_and_unparseable_registry_are_exit_2(tmp_path):
    assert run("check", str(tmp_path / "regress.toml")) == 2
    bad = tmp_path / "regress.toml"
    bad.write_text("[golden.x\nactual =", encoding="utf-8")
    assert run("check", str(bad)) == 2


def test_missing_lock_is_exit_2_and_says_freeze(proj, capsys):
    tmp, reg = proj
    assert run("check", str(reg)) == 2
    assert "run freeze first" in capsys.readouterr().err


def test_missing_actual_file_is_exit_2(proj):
    tmp, reg = proj
    freeze(reg)
    (tmp / "out" / "results.json").unlink()
    assert run("check", str(reg)) == 2


def test_unparseable_actual_is_exit_2(proj):
    tmp, reg = proj
    freeze(reg)
    (tmp / "out" / "results.json").write_text("{not json", encoding="utf-8")
    assert run("check", str(reg)) == 2


def test_key_not_found_is_exit_2(proj, capsys):
    tmp, reg = proj
    freeze(reg)
    write_results(tmp, other=1.0)
    assert run("check", str(reg)) == 2
    assert "not found" in capsys.readouterr().out


def test_bool_actual_is_exit_2(proj):
    tmp, reg = proj
    freeze(reg)
    write_results(tmp, mpsp=True)
    assert run("check", str(reg)) == 2


def test_string_actual_is_exit_2(proj):
    tmp, reg = proj
    freeze(reg)
    write_results(tmp, mpsp="100.0")
    assert run("check", str(reg)) == 2


def test_toml_actual_and_dotted_path(tmp_path):
    (tmp_path / "res.toml").write_text("[economics]\nmpsp = 3.17\n", encoding="utf-8")
    reg = write_registry(tmp_path, {"mpsp": {"actual": "res.toml:economics.mpsp"}})
    assert freeze(reg) == 0
    assert run("check", str(reg)) == 0


def test_golden_absent_from_lock_is_exit_2(tmp_path, capsys):
    write_results(tmp_path, a=1.0, b=2.0)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}})
    freeze(reg)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}, "b": {"actual": "out/results.json:b"}})
    assert run("check", str(reg)) == 2
    assert "never frozen" in capsys.readouterr().out


def test_moved_and_missing_other_together_is_exit_1(tmp_path):
    write_results(tmp_path, a=1.0, b=2.0)
    reg = write_registry(
        tmp_path,
        {"a": {"actual": "out/results.json:a", "rtol": 0.01}, "b": {"actual": "out/results.json:b"}},
    )
    freeze(reg)
    write_results(tmp_path, a=9.0)  # a moved, b now missing
    assert run("check", str(reg)) == 1


def test_lock_orphan_is_violation_needs_review(tmp_path, capsys):
    write_results(tmp_path, a=1.0, b=2.0)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}, "b": {"actual": "out/results.json:b"}})
    freeze(reg)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}})
    capsys.readouterr()
    assert run("check", str(reg), "--format", "json") == 1
    doc = json.loads(capsys.readouterr().out)
    orphan = [f for f in doc["findings"] if f["rule"] == "lock-orphan"][0]
    assert orphan["status"] == "violation"
    assert orphan["confidence"] == "needs_review"
    assert orphan["fix"] == {
        "applicability": "safe",
        "apply": "suggest_only",
        "edit": orphan["fix"]["edit"],
    }


def test_full_freeze_retires_orphan_on_record_but_only_does_not(tmp_path):
    write_results(tmp_path, a=1.0, b=2.0)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}, "b": {"actual": "out/results.json:b"}})
    freeze(reg)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}})
    freeze(reg, "b dropped", "--only", "a")
    assert "b" in lock_of(tmp_path)["goldens"]
    freeze(reg, "b was superseded by a")
    lock = lock_of(tmp_path)
    assert "b" not in lock["goldens"]
    assert lock["retired"][0]["id"] == "b" and lock["retired"][0]["reason"] == "b was superseded by a"
    assert run("check", str(reg)) == 0


def test_history_records_old_new_reason_and_unchanged_adds_nothing(proj):
    tmp, reg = proj
    freeze(reg, "initial freeze")
    write_results(tmp, mpsp=110.0)
    freeze(reg, "new solver version")
    history = lock_of(tmp)["goldens"]["mpsp"]["history"]
    assert [(h["old"], h["new"], h["reason"]) for h in history] == [
        (None, 100.0, "initial freeze"),
        (100.0, 110.0, "new solver version"),
    ]
    assert freeze(reg, "no-op refreeze") == 0
    assert len(lock_of(tmp)["goldens"]["mpsp"]["history"]) == 2


def test_only_freezes_a_subset(tmp_path):
    write_results(tmp_path, a=1.0, b=2.0)
    reg = write_registry(tmp_path, {"a": {"actual": "out/results.json:a"}, "b": {"actual": "out/results.json:b"}})
    assert freeze(reg, "just a", "--only", "a") == 0
    assert list(lock_of(tmp_path)["goldens"]) == ["a"]
    assert freeze(reg, "typo", "--only", "zzz") == 2


def test_history_command(proj, capsys):
    tmp, reg = proj
    freeze(reg, "initial freeze")
    assert run("history", "mpsp", "--registry", str(reg)) == 0
    assert "reason: initial freeze" in capsys.readouterr().out
    assert run("history", "nope", "--registry", str(reg)) == 2


STUB = shlex.join([sys.executable, "-c", "print('hi from stub')"])


def test_explain_runs_stub_and_appends_output(proj, capsys):
    tmp, reg = proj
    write_registry(tmp, explain=[STUB])
    freeze(reg)
    write_results(tmp, mpsp=150.0)
    assert run("check", str(reg), "--explain") == 1
    out = capsys.readouterr().out
    assert f"--- explain: {STUB} (exit 0) ---" in out
    assert "hi from stub" in out


def test_without_explain_flag_prints_hint_and_runs_nothing(proj, capsys):
    tmp, reg = proj
    write_registry(tmp, explain=[STUB])
    freeze(reg)
    write_results(tmp, mpsp=150.0)
    assert run("check", str(reg)) == 1
    out = capsys.readouterr().out
    assert "hint: rerun with --explain" in out and "--- explain:" not in out


def test_explain_not_run_when_clean(proj, capsys):
    tmp, reg = proj
    write_registry(tmp, explain=[STUB])
    freeze(reg)
    assert run("check", str(reg), "--explain") == 0
    assert "hi from stub" not in capsys.readouterr().out


def test_missing_explain_executable_reported_inline(proj, capsys):
    tmp, reg = proj
    write_registry(tmp, explain=["definitely-not-a-real-exe-xyz --flag", STUB])
    freeze(reg)
    write_results(tmp, mpsp=150.0)
    assert run("check", str(reg), "--explain") == 1
    out = capsys.readouterr().out
    assert "definitely-not-a-real-exe-xyz --flag (not run: executable not found)" in out
    assert "hi from stub" in out  # later commands still run


def test_explain_tail_is_last_40_lines(proj, capsys):
    tmp, reg = proj
    noisy = shlex.join([sys.executable, "-c", "print('\\n'.join(f'L{i}' for i in range(100)))"])
    write_registry(tmp, explain=[noisy])
    freeze(reg)
    write_results(tmp, mpsp=150.0)
    run("check", str(reg), "--explain")
    out = capsys.readouterr().out
    assert "L99" in out and "L60" in out and "L59" not in out


def test_json_output_parses_with_schema_and_summary(proj, capsys):
    tmp, reg = proj
    freeze(reg)
    capsys.readouterr()
    write_results(tmp, mpsp=150.0)
    assert run("check", str(reg), "--format", "json") == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["summary"] == {"checked": 1, "violations": 1, "cannot_check": 0}
    f = doc["findings"][0]
    assert f["rule"] == "moved" and f["status"] == "violation" and f["confidence"] == "certain"
    assert f["fix"]["apply"] == "suggest_only" and f["fix"]["applicability"] == "unsafe"


def test_json_output_on_fatal_is_a_cannot_check_finding(tmp_path, capsys):
    assert run("check", str(tmp_path / "regress.toml"), "--format", "json") == 2
    doc = json.loads(capsys.readouterr().out)
    assert doc["findings"][0]["status"] == "cannot_check"
    assert doc["summary"]["cannot_check"] == 1


def test_python_dash_m_works(proj):
    import subprocess

    tmp, reg = proj
    freeze(reg)
    proc = subprocess.run(
        [sys.executable, "-m", "regress_check", "check", str(reg)],
        capture_output=True, encoding="utf-8", errors="replace",
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert proc.returncode == 0, proc.stderr


def test_critical_tag_shown_and_invalid_tag_rejected(tmp_path, capsys):
    write_results(tmp_path, mpsp=100.0)
    reg = write_registry(tmp_path, {"mpsp": {"actual": "out/results.json:mpsp", "critical": "manuscript"}})
    freeze(reg)
    write_results(tmp_path, mpsp=200.0)
    run("check", str(reg))
    assert "critical=manuscript" in capsys.readouterr().out
    write_registry(tmp_path, {"mpsp": {"actual": "out/results.json:mpsp", "critical": "vibes"}})
    assert run("check", str(reg)) == 2


def test_relative_registry_path_resolves_paths_against_registry_dir(proj, monkeypatch, tmp_path_factory):
    tmp, reg = proj
    freeze(reg)
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
    assert run("check", str(reg)) == 0
