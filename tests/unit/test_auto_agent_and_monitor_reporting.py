from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from modules.trae_test.orchestrator.auto_agent import AutoAgent, ConfirmationService, RiskLevel
from modules.trae_test.orchestrator.config import OutputMode
from modules.trae_test.orchestrator.monitor import LogLevel, WorkflowMonitor, WorkflowReporter
from modules.trae_test.orchestrator.workflow_manager import StepStatus, StepType, Workflow, WorkflowStatus, WorkflowStep

pytestmark = pytest.mark.unit


def _case(**kwargs):
    data = {
        "用例编号": "TC-1",
        "用例名称": "case",
        "用例类型": "功能测试",
        "测试步骤": "1. open\n2. call API\n3. query",
        "预期结果": "ok",
    }
    data.update(kwargs)
    return data


class TestAutoAgent:
    def test_analyze_cases_recommends_frameworks_dependencies_and_resources(self):
        agent = AutoAgent()
        cases = [_case(), _case(用例类型="接口测试"), _case(用例类型="单元测试"), _case(用例类型="性能测试")]

        analysis = agent.analyze_cases(cases)

        assert analysis["total_cases"] == 4
        assert analysis["auto_candidate_count"] >= 3
        assert analysis["manual_only_count"] >= 0
        assert analysis["framework_recommendations"]
        assert analysis["resource_requirements"]["cpu_cores"] >= 2
        assert any(dep["mock_required"] for dep in analysis["external_dependencies"])

    def test_candidate_framework_resource_and_mock_helpers(self):
        agent = AutoAgent()
        assert agent._is_automation_candidate(_case())
        assert not agent._is_automation_candidate(_case(用例类型="性能测试"))
        assert agent._estimate_resources(200)["cpu_cores"] == 8

        analysis = {
            "framework_recommendations": [
                {"framework": "Playwright"},
                {"framework": "Postman"},
            ],
            "resource_requirements": {"cpu_cores": 4, "memory_gb": 8, "storage_gb": 2, "network_bandwidth_mbps": 100},
            "external_dependencies": [
                {"type": "API服务", "description": "api", "mock_required": True},
                {"type": "database", "description": "db", "mock_required": False},
            ],
        }

        assert agent._generate_framework_plan(analysis)["primary_framework"] == "Playwright"
        assert "tests/" in agent._generate_directory_structure(analysis)
        assert agent._generate_execution_environment(analysis)["hardware"]["cpu"] == "4 cores"
        assert agent._generate_mock_strategy(analysis)[0]["mock_data_required"] is True

    def test_generate_solution_risk_report_and_confirmation_service(self):
        agent = AutoAgent()
        cases = [
            _case(用例编号="TC-H", 用例名称="delete", 测试步骤="删除 order"),
            _case(用例编号="TC-M", 用例名称="pay", 测试步骤="支付 金额"),
            _case(用例编号="TC-L", 用例名称="query", 测试步骤="查询 order"),
        ]

        solution = agent.generate_solution("wf-1", cases)
        report = agent.generate_markdown_report(solution)
        confirmation = ConfirmationService()
        approved = confirmation.confirm_solution("wf-1", True, "ok")
        rejected = confirmation.confirm_solution("wf-2", False, "no")

        assert solution["workflow_id"] == "wf-1"
        assert "risk_assessment" in solution
        assert agent._get_risk_suggestion(RiskLevel.HIGH)
        assert "wf-1" in report
        assert approved["confirmed"] is True
        assert rejected["confirmed"] is False
        assert confirmation.get_confirmation("wf-2")["status"] == "rejected"
        assert confirmation.get_confirmation("wf-1")["confirmed"] is True
        confirmation.reset_confirmation("wf-1")
        assert confirmation.get_confirmation("wf-1") is None


class TestWorkflowMonitorReporter:
    def test_monitor_logs_colors_progress_headers_and_summary(self, capsys):
        monitor = WorkflowMonitor(output_mode=OutputMode.CONSOLE)
        monitor.enable_colors = True

        monitor.log("hello", LogLevel.INFO)
        monitor.log_progress(2, 4, "half")
        monitor.log_progress(1, 0)
        monitor.log_header("Title")
        monitor.log_subheader("Sub")
        monitor.log_error(RuntimeError("boom"), context="ctx")
        summary = monitor.get_summary()
        captured = capsys.readouterr()

        assert "hello" in captured.out
        assert monitor._get_color(LogLevel.ERROR)
        assert summary["total_logs"] >= 5
        assert summary["error_count"] == 1

    def test_monitor_step_and_audit_logging(self):
        monitor = WorkflowMonitor(output_mode=OutputMode.REPORT)
        step = WorkflowStep("s1", "Step 1", StepType.AGENT)
        step.description = "desc"
        step.status = StepStatus.PASSED
        step.start_time = datetime.now() - timedelta(seconds=2)
        step.end_time = datetime.now()

        monitor.log_step_start(step)
        monitor.log_step_complete(step)
        monitor.log_audit(SimpleNamespace(passed=True, errors=[]), "case")
        monitor.log_audit(SimpleNamespace(passed=False, errors=[{"message": "bad"}] * 4), "case")

        assert any("Step 1" in log["message"] for log in monitor.logs)
        assert any(log["level"] == "ERROR" for log in monitor.logs)

    def test_reporter_generates_and_saves_workflow_reports(self, tmp_path):
        monitor = WorkflowMonitor(output_mode=OutputMode.REPORT)
        monitor.log("warn", LogLevel.WARNING)
        workflow = Workflow("wf-1", "Demo")
        step_passed = WorkflowStep("s1", "Passed", StepType.AGENT)
        step_passed.status = StepStatus.PASSED
        step_failed = WorkflowStep("s2", "Failed", StepType.AUDIT)
        step_failed.status = StepStatus.FAILED
        workflow.steps = [step_passed, step_failed]
        workflow.status = WorkflowStatus.FAILED
        workflow.error_message = "failed"
        reporter = WorkflowReporter(monitor)

        report = reporter.generate_report(workflow, include_logs=True)
        output = tmp_path / "reports" / "workflow.txt"
        reporter.save_report(workflow, str(output), include_logs=True)
        summary = reporter.generate_summary_report([workflow])

        assert "wf-1" in report
        assert "failed" in report
        assert output.exists()
        assert "Demo" in summary
