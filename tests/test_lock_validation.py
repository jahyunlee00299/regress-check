import json

import pytest

from regress_check.cli import main

GOOD = {"expected": 1.0, "rtol": 1e-6, "atol": 0.0, "history": []}


def _project(tmp_path, entry):
    (tmp_path / "regress.toml").write_text('[golden.a]\nactual = "r.json:x"\n', encoding="utf-8")
    (tmp_path / "r.json").write_text('{"x": 1.0}', encoding="utf-8")
    (tmp_path / "regress.lock.json").write_text(json.dumps({"version": 1, "goldens": {"a": entry}}), encoding="utf-8")
    return str(tmp_path / "regress.toml")


@pytest.mark.parametrize(
    "entry",
    [
        {"expected": 1.0, "atol": 0.0, "history": []},
        {**GOOD, "expected": "1.0"},
        {**GOOD, "rtol": True},
        {"expected": 1.0, "rtol": 1e-6, "atol": 0.0},
        "oops",
    ],
    ids=["missing-rtol", "string-expected", "bool-rtol", "missing-history", "not-an-object"],
)
@pytest.mark.parametrize("cmd", ["check", "history"])
def test_malformed_lock_entry_is_cannot_check_not_a_traceback(tmp_path, monkeypatch, capsys, entry, cmd):
    monkeypatch.setenv("NO_UPDATE_CHECK", "1")
    reg = _project(tmp_path, entry)
    argv = ["check", reg] if cmd == "check" else ["history", "--registry", reg]
    assert main(argv) == 2
    assert "malformed" in capsys.readouterr().err + ""


def test_malformed_lock_entry_blocks_freeze(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_UPDATE_CHECK", "1")
    reg = _project(tmp_path, {"expected": 2.0, "rtol": 1e-6, "atol": 0.0})
    assert main(["freeze", reg, "--reason", "r"]) == 2


def test_well_formed_lock_still_checks_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_UPDATE_CHECK", "1")
    assert main(["check", _project(tmp_path, GOOD)]) == 0
