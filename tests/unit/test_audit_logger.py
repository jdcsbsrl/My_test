"""测试审核日志持久化"""

from modules.trae_test.orchestrator.audit_logger import AuditLogger
from modules.trae_test.orchestrator.audit_models import AuditResult


class TestAuditLogger:
    def test_create_logger(self):
        """测试创建日志管理器"""
        logger = AuditLogger()
        assert logger is not None

    def test_log_and_query(self):
        """测试记录日志并查询"""
        logger = AuditLogger()

        result = AuditResult()
        result.add_error("ERR1", "test error")

        log_id = logger.log(result, {"source": "unittest"})
        assert log_id > 0

        logs = logger.query(limit=10)
        assert len(logs) >= 1
        assert logs[0]["passed"] is False

    def test_log_passed_result(self):
        """测试记录通过的审核结果"""
        logger = AuditLogger()

        result = AuditResult()
        log_id = logger.log(result)
        assert log_id > 0

    def test_get_summary(self):
        """测试获取摘要统计"""
        logger = AuditLogger()

        logger.log(AuditResult())
        logger.log(AuditResult())

        summary = logger.get_summary()
        assert summary["total"] >= 2

    def test_to_storage_dict_serialization(self):
        """测试 to_storage_dict 序列化所有字段"""
        result = AuditResult()
        result.issues.append(
            AuditResult.__annotations__.get('issues', list).__args__[0](
                severity="manual_review",
                rule_id="REVIEW_001",
                category="approval",
                message="需人工确认",
                location="test",
                fix_hint="建议修改",
                confidence=0.85,
            )
        )

        storage = result.to_storage_dict()
        assert "issues" in storage
        assert len(storage["issues"]) == 1
        issue = storage["issues"][0]
        assert issue["severity"] == "manual_review"
        assert issue["rule_id"] == "REVIEW_001"
        assert issue["category"] == "approval"
        assert issue["location"] == "test"
        assert issue["fix_hint"] == "建议修改"
        assert issue["confidence"] == 0.85
