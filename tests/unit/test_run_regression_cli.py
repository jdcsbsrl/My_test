"""回归命令入口的预览/执行门槛契约。

正式回归入口默认只输出计划，必须显式传 `--execute` 才触发真实查询。
"""

import sys

import pytest

from tools import run_regression as cli

pytestmark = pytest.mark.unit


class _FakeReport:
    def __init__(self, status: str = "PASS", can_deliver: bool = True):
        self.release_decision = {"status": status, "can_deliver": can_deliver}


def _run(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["run_regression.py", *argv])
    return cli.main()


def test_scope_without_execute_only_previews(monkeypatch, capsys):
    executed = []
    monkeypatch.setattr(cli, "run_regression_tests", lambda **kwargs: executed.append(kwargs))

    exit_code = _run(monkeypatch, ["--env", "test", "--scope", "smoke"])

    assert exit_code == 0
    assert executed == []
    output = capsys.readouterr().out
    assert "回归计划" in output
    assert "smoke" in output
    assert "--execute" in output


def test_scope_with_execute_runs_regression(monkeypatch):
    executed = []
    monkeypatch.setattr(cli, "run_regression_tests", lambda **kwargs: executed.append(kwargs) or _FakeReport())

    exit_code = _run(monkeypatch, ["--env", "uat", "--scope", "module", "--execute"])

    assert exit_code == 0
    assert executed == [{"env_name": "uat", "scope": "module"}]


def test_blocked_regression_reports_blocked_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_regression_tests", lambda **kwargs: _FakeReport(status="BLOCKED", can_deliver=False))

    assert _run(monkeypatch, ["--scope", "release", "--execute"]) == 1


def test_undeliverable_regression_reports_warning_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_regression_tests", lambda **kwargs: _FakeReport(status="PASS", can_deliver=False))

    assert _run(monkeypatch, ["--scope", "module", "--execute"]) == 2


def test_production_environment_is_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_regression.py", "--env", "prod", "--execute"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 2
