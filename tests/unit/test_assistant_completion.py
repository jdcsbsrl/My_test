"""Regression counterexamples found while exercising the real CLI workflow."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.auto_test.core.regression_checks import order_rows
from modules.auto_test.core.registered_regression import validate_script_node, plan_registered_cases
from modules.trae_test.utils.case_health import case_health
from modules.trae_test.utils.case_registry import CaseRegistry
from modules.trae_test.utils.runtime_quality import RuntimeQualitySnapshot, attach_runtime_quality
from modules.trae_test.utils.template_builder import ALL_FIELDS


def audited_case(title="示例订单查询"):
    case = dict.fromkeys(ALL_FIELDS, "示例")
    case.update({"需求ID": "REQ-DEMO", "用例名称": title, "优先级": "P1", "质量评分": 100})
    attach_runtime_quality(case, RuntimeQualitySnapshot(final_audit_passed=True))
    return case


def test_real_nested_response_is_parsed_but_nested_failure_is_rejected():
    table = {"code": 200, "rows": [{"orderNo": "DEMO"}]}
    response = SimpleNamespace(status_code=200, json=lambda: {"code": 200, "data": {"tableDataInfo": table}})
    assert order_rows(response) == table["rows"]
    table["code"] = 500
    with pytest.raises(AssertionError, match="Nested"):
        order_rows(response)


def test_session_scopes_credentials_and_cleans_up_after_query_error(monkeypatch):
    import modules.auto_test.core.regression_session as sessions

    monkeypatch.setattr(sessions, "check_authorization", lambda: None)
    config = SimpleNamespace(env="uat", api_base_url="https://uat.example.invalid/api")
    monkeypatch.setattr(sessions, "get_environment", lambda env: config)
    lookup = Mock(return_value=None)
    monkeypatch.setattr(sessions, "get_secret", lookup)
    credentials = {"token": "fake-token", "clientid": "fake-client", "cookies": []}
    login = Mock(return_value=credentials)
    monkeypatch.setattr(sessions, "_browser_authentication", login)
    client = Mock()
    monkeypatch.setattr(sessions, "APIClient", Mock(return_value=client))
    with pytest.raises(RuntimeError, match="query failed"):
        with sessions.regression_session("uat"):
            raise RuntimeError("query failed")
    assert all(call.kwargs["environment"] == "uat" for call in lookup.call_args_list)
    login.assert_called_once_with(config)
    client.clear_auth.assert_called_once()
    client.close.assert_called_once()
    assert credentials == {}


def test_browser_authentication_uses_the_explicit_session_configuration(monkeypatch):
    import modules.auto_test.core.regression_session as sessions
    import modules.auto_test.drivers.browser_driver as browser_driver
    import modules.auto_test.pages.login_page as login_page_module

    session_config = SimpleNamespace(env="uat", api_base_url="https://uat.example.invalid/api")
    monkeypatch.setattr(sessions, "get_secret", lambda *args, **kwargs: "secret")
    driver = Mock()
    browser = Mock()
    context = Mock()
    page = Mock()
    browser.new_context.return_value = context
    context.new_page.return_value = page
    context.cookies.return_value = []
    driver.start_browser.return_value = browser

    def driver_factory(*, config, **kwargs):
        assert config is session_config
        return driver

    monkeypatch.setattr(browser_driver, "BrowserDriver", driver_factory)

    login_page = Mock()
    login_page.login.return_value = True

    def login_page_factory(page, *, config):
        assert config is session_config
        return login_page

    monkeypatch.setattr(login_page_module, "LoginPage", login_page_factory)

    # The response hook does not need to fire for this configuration-wiring test.
    with pytest.raises(RuntimeError, match="usable session"):
        sessions._browser_authentication(session_config)

    assert driver.start_browser.called
    assert driver.shutdown_browser.called


def test_session_rejects_production_before_authentication(monkeypatch):
    import modules.auto_test.core.regression_session as sessions

    login = Mock()
    monkeypatch.setattr(sessions, "_browser_authentication", login)
    with pytest.raises(ValueError):
        with sessions.regression_session("production"):
            pytest.fail("must not yield")
    login.assert_not_called()


def test_production_generation_does_not_fall_back_to_generic_local_steps():
    from modules.trae_test.utils.case_generation_service import CaseGenerationService

    retriever = Mock()
    retriever.retrieve.return_value = [{"content": {"description": "An existing business rule"}}]
    service = CaseGenerationService(retriever=retriever, gateway=Mock(), rules={})
    result = service.generate("query orders", "REQ-DEMO")
    assert result["status"] == "generation_failed"
    assert result["cases"] == []
    assert result["questions"] == []


def test_candidate_cannot_supply_its_own_audit_pass():
    from modules.trae_test.utils.case_generation_service import CaseGenerationService
    from modules.trae_test.orchestrator.audit_models import AuditResult

    retriever = Mock()
    retriever.retrieve.return_value = [{"content": "query contract"}]
    gateway = Mock()
    failure = AuditResult()
    failure.add_error("TC_STEPS_EMPTY", "Missing steps")
    gateway.audit.return_value = failure
    service = CaseGenerationService(retriever=retriever, gateway=gateway, rules={})
    case = audited_case()
    case["用例步骤"] = ""
    result = service.generate("query orders", "REQ-DEMO", candidate=case)
    assert result["status"] == "generation_failed"
    assert result["cases"][0]["_runtime_quality"]["final_audit_passed"] is False


def test_existing_file_with_removed_test_is_not_an_executable_binding():
    with pytest.raises(ValueError, match="no longer exists"):
        validate_script_node("modules/auto_test/tests/test_registered_query_smoke.py::test_removed")


def test_script_change_requires_new_version_and_keeps_previous_evidence(tmp_path, monkeypatch):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    script = "modules/auto_test/tests/test_registered_query_smoke.py::test_sales_order_query_smoke"
    monkeypatch.setattr(registry, "script_digest", lambda script: "before")
    case = audited_case()
    case_id, version = registry.save(case, "REQ-DEMO", script_id=script)
    registry.record_execution(case_id, version, "PASS", "old-evidence.xml")
    monkeypatch.setattr(registry, "script_digest", lambda script: "after")
    with pytest.raises(ValueError, match="script changed"):
        plan_registered_cases(registry, [case_id])
    assert "script_changed" in case_health(registry)["issues"][0]["signals"]
    assert registry.save(case, "REQ-DEMO", case_id=case_id, script_id=script, reason="reviewed script change")[1] == 2
    history = registry.list_cases(active_only=False)
    assert history[0]["last_status"] == "PASS"
    assert history[1]["last_status"] is None


def test_health_detects_title_variants_without_retiring_them(tmp_path):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    for title in ("订单查询", "查看订单列表"):
        registry.save(audited_case(title), "REQ-DEMO")
    report = case_health(registry)
    assert len(report["similar_candidates"]) == 1
    assert len(report["issues"]) == 2
    assert len(registry.list_cases()) == 2


@pytest.mark.parametrize("xml", ["<broken", "<testsuites><testsuite><error/></testsuite></testsuites>"])
def test_invalid_or_suite_error_evidence_never_passes(tmp_path, monkeypatch, xml):
    import modules.auto_test.core.registered_regression as runner
    import modules.auto_test.core.config_manager as config
    import modules.auto_test.core.execution_auth as auth
    from pathlib import Path

    monkeypatch.setattr(auth, "check_authorization", lambda: None)
    monkeypatch.setattr(config, "get_environment", lambda env: None)
    monkeypatch.setattr(runner, "runtime_dir", lambda kind: tmp_path)

    def run(command, **kwargs):
        path = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml=")))
        path.write_text(xml, encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    registry = Mock()
    assert (
        runner.run_registered_cases(
            registry, [{"case_id": "TC-DEMO", "version": 1, "script_id": "unused::test_demo"}], "uat"
        )
        != 0
    )
    summary = next(tmp_path.rglob("summary.json"))
    assert json.loads(summary.read_text(encoding="utf-8"))["summary"]["passed"] == 0
