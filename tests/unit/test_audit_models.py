"""测试审核结果模型"""

from modules.trae_test.orchestrator.audit_models import AuditIssue, AuditResult


class TestAuditIssue:
    def test_create_error_issue(self):
        issue = AuditIssue(
            severity="error",
            rule_id="TC_FIELD_001",
            category="field_value",
            message="字段值无效",
            location="用例1",
            fix_hint="请使用合法值",
            confidence=0.95,
        )
        assert issue.severity == "error"
        assert issue.rule_id == "TC_FIELD_001"
        assert issue.confidence == 0.95

    def test_create_warning_issue(self):
        issue = AuditIssue(
            severity="warning", rule_id="WARN_001", category="style", message="建议优化"
        )
        assert issue.severity == "warning"
        assert issue.location == ""
        assert issue.fix_hint is None

    def test_create_manual_review_issue(self):
        issue = AuditIssue(
            severity="manual_review",
            rule_id="REVIEW_001",
            category="approval",
            message="需人工确认",
        )
        assert issue.severity == "manual_review"


class TestAuditResult:
    def test_default_construction(self):
        result = AuditResult()
        assert result.passed is True
        assert result.issues == []
        assert result.suggestions == []
        assert result.score is None
        assert result.audit_type is None
        assert result.timestamp != ""

    def test_errors_property_from_issues(self):
        result = AuditResult()
        result.issues.append(
            AuditIssue(
                severity="error", rule_id="ERR1", category="test", message="错误1"
            )
        )
        result.issues.append(
            AuditIssue(
                severity="warning",
                rule_id="WARN1",
                category="test",
                message="警告1",
            )
        )

        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "ERR1"
        assert result.errors[0]["message"] == "错误1"
        assert len(result.warnings) == 1
        assert result.warnings[0]["code"] == "WARN1"

    def test_passed_false_when_errors_exist(self):
        result = AuditResult()
        assert result.passed is True
        result.issues.append(
            AuditIssue(
                severity="error", rule_id="ERR1", category="test", message="错误"
            )
        )
        # passed 自动从 issues 计算
        assert result.passed is False

    def test_passed_dynamic_calculation(self):
        """测试 passed 随 issues 动态变化"""
        result = AuditResult()
        assert result.passed is True

        result.issues.append(AuditIssue(severity="error", rule_id="ERR1", category="test", message="error"))
        assert result.passed is False

        result.issues.clear()
        assert result.passed is True

    def test_passed_setter_forced(self):
        """测试 passed setter 强制设置生效"""
        result = AuditResult()
        assert result.passed is True

        result.passed = False
        assert result.passed is False

        result.issues.clear()
        assert result.passed is False  # 仍然保持强制设置的值

    def test_add_error_deprecated(self):
        result = AuditResult()
        result.add_error("ERR001", "错误描述", "location")
        assert len(result.issues) == 1
        assert result.issues[0].severity == "error"
        assert result.issues[0].rule_id == "ERR001"
        # passed 由 property 从 issues 动态计算
        assert result.passed is False

    def test_add_warning_deprecated(self):
        result = AuditResult()
        result.add_warning("WARN001", "警告描述", "location")
        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is True  # 警告不影响通过

    def test_add_suggestion(self):
        result = AuditResult()
        result.add_suggestion("建议优化")
        assert result.suggestions == ["建议优化"]

    def test_to_dict_format(self):
        result = AuditResult()
        result.add_error("ERR1", "错误", "loc")
        result.add_warning("WARN1", "警告", "loc")
        result.add_suggestion("建议")
        result.execution_time = 1.23

        d = result.to_dict()
        assert d["passed"] is False
        assert len(d["errors"]) == 1
        assert len(d["warnings"]) == 1
        assert len(d["suggestions"]) == 1
        assert d["error_count"] == 1
        assert d["warning_count"] == 1
        assert d["execution_time"] == 1.23
        assert "timestamp" in d

    def test_str_representation(self):
        result = AuditResult()
        assert "[通过]" in str(result)
        result.add_error("ERR1", "错误")
        assert "[未通过]" in str(result)

    def test_score_field(self):
        result = AuditResult(score=85.5)
        assert result.score == 85.5
        d = result.to_dict()
        assert "score" not in d  # to_dict 保持原格式，不含 score
