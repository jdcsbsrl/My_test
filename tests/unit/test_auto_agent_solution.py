import pytest

from modules.trae_test.orchestrator.auto_agent import AutoAgent, ConfirmationService, RiskLevel


pytestmark = pytest.mark.unit


def test_analyze_cases_defaults_to_automation_candidates():
    agent = AutoAgent()

    analysis = agent.analyze_cases([{}, {"测试步骤": "1. open\n2. save"}])

    assert analysis["total_cases"] == 2
    assert analysis["auto_candidate_count"] == 2
    assert analysis["manual_only_count"] == 0
    assert analysis["resource_requirements"]["cpu_cores"] == 2
    assert analysis["analysis_time_ms"] >= 0


def test_recommend_frameworks_orders_by_applicable_count():
    agent = AutoAgent()
    cases = [{}, {}, {"用例类型": "接口测试"}, {"用例类型": "单元测试"}]

    recommendations = agent._recommend_frameworks(cases)

    assert recommendations[0]["framework"] == "Playwright"
    assert recommendations[0]["applicable_case_count"] == 2
    assert recommendations[0]["recommendation_level"] == "MEDIUM"


def test_generate_solution_contains_expected_sections():
    agent = AutoAgent()

    solution = agent.generate_solution("wf-60", [{}])

    assert solution["workflow_id"] == "wf-60"
    assert solution["framework_plan"]["primary_framework"] == "Playwright"
    assert "tests/" in solution["directory_structure"]
    assert solution["execution_environment"]["hardware"]["cpu"] == "2 cores"
    assert solution["risk_assessment"]["total_risks"] == 0
    assert solution["generation_time_ms"] >= 0


def test_framework_environment_mock_strategy_and_risk_helpers():
    agent = AutoAgent()
    analysis = {
        "framework_recommendations": [
            {"framework": "Playwright"},
            {"framework": "Postman"},
        ],
        "resource_requirements": {
            "cpu_cores": 6,
            "memory_gb": 8,
            "storage_gb": 3,
            "network_bandwidth_mbps": 100,
        },
        "external_dependencies": [
            {"type": "API服务", "description": "backend", "mock_required": True},
            {"type": "database", "description": "db", "mock_required": False},
        ],
    }

    assert agent._generate_framework_plan(analysis)["secondary_frameworks"] == ["Postman"]
    assert agent._generate_execution_environment(analysis)["hardware"]["memory"] == "8 GB RAM"
    assert agent._generate_mock_strategy(analysis) == [
        {
            "dependency_type": "API服务",
            "description": "backend",
            "mock_tool": "MockServiceWorker",
            "mock_data_required": True,
        }
    ]
    assert agent._get_risk_suggestion(RiskLevel.LOW)


def test_generate_markdown_report_uses_solution_values():
    agent = AutoAgent()
    solution = {
        "workflow_id": "wf-1",
        "generated_at": "2026-07-27T10:00:00",
        "generation_time_ms": 12.3,
        "analysis": {
            "total_cases": 1,
            "auto_candidate_count": 1,
            "manual_only_count": 0,
            "estimated_execution_time_minutes": 1.5,
        },
        "framework_plan": {"primary_framework": "Playwright", "secondary_frameworks": ["Postman"]},
        "directory_structure": "tests/",
        "external_dependencies": [{"type": "API", "description": "backend", "mock_required": True}],
        "execution_environment": {
            "hardware": {"cpu": "2 cores", "memory": "4 GB RAM", "storage": "2 GB"},
            "software": {"node_version": "18", "python_version": "3.14"},
        },
        "risk_assessment": {
            "high_risk_count": 1,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "risks": [
                {
                    "case_name": "delete order",
                    "case_id": "TC-1",
                    "risk_level": "HIGH",
                    "risk_description": "delete",
                    "affected_data": ["order"],
                    "suggestion": "backup",
                }
            ],
        },
        "mock_strategy": [{"dependency_type": "API", "mock_tool": "WireMock", "mock_data_required": True}],
    }

    report = agent.generate_markdown_report(solution)

    assert "wf-1" in report
    assert "Playwright" in report
    assert "delete order" in report
    assert "WireMock" in report


def test_confirmation_service_confirm_get_and_reset():
    service = ConfirmationService()

    result = service.confirm_solution("wf-1", False, "needs changes")

    assert result["success"] is True
    assert result["confirmed"] is False
    assert service.get_confirmation("wf-1")["status"] == "rejected"
    service.reset_confirmation("wf-1")
    assert service.get_confirmation("wf-1") is None
