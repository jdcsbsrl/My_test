"""测试审核网关"""

from modules.trae_test.orchestrator.audit_gateway import AuditGateway
from modules.trae_test.orchestrator.audit_models import AuditResult


class TestAuditGateway:
    def test_create_gateway(self):
        gw = AuditGateway()
        assert gw is not None

    def test_audit_disabled(self):
        from modules.trae_test.orchestrator.config import AuditConfig

        config = AuditConfig(enabled=False)
        gw = AuditGateway(config)
        result = gw.audit(["test"], "test_case")
        assert result.passed is True
        assert result.execution_time == 0.0

    def test_audit_test_cases(self):
        gw = AuditGateway()
        cases = [
            {
                "用例目录": "模块",
                "用例名称": "测试用例",
                "需求ID": "1001",
                "前置条件": "登录",
                "用例步骤": "1.操作",
                "预期结果": "成功",
                "用例类型": "功能测试",
                "用例状态": "正常",
                "用例等级": "高",
                "创建人": "余小龙",
                "优先级": "P1",
                "是否可自动化": "是",
                "关联缺陷ID": "",
                "回归测试标识": "否",
                "知识库关联": "",
            }
        ]
        result = gw.audit_test_cases(cases)
        assert isinstance(result, AuditResult)
        # 合法的用例应通过
        assert result.passed is True

    def test_audit_code(self):
        gw = AuditGateway()
        code = "def hello():\n    print('Hello World')"
        result = gw.audit_code(code)
        assert isinstance(result, AuditResult)

    def test_audit_security(self):
        gw = AuditGateway()
        code = "password = 'xxx'"  # 安全值（xxx被正则排除）
        result = gw.audit_security(code)
        # xxx 是安全值，不应检测到敏感信息
        assert result.passed is True

    def test_audit_environment(self):
        gw = AuditGateway()
        env = {"python_version": "3.14", "dependencies": ["pytest"]}
        result = gw.audit_environment(env)
        assert isinstance(result, AuditResult)

    def test_audit_impact(self):
        gw = AuditGateway()
        result = gw.audit_impact([], {"file_path": "test.py"})
        assert isinstance(result, AuditResult)

    def test_query_logs(self):
        gw = AuditGateway()
        gw.logger.query = lambda **kwargs: [{"id": 1, "limit": kwargs.get("limit")}]
        logs = gw.query_logs(limit=10)
        assert logs == [{"id": 1, "limit": 10}]

    def test_get_summary(self):
        gw = AuditGateway()
        summary = gw.get_summary()
        assert isinstance(summary, dict)
