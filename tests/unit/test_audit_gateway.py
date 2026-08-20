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
                "用例目录": "产品 - 产品中心 - 库存SKU",
                "用例名称": "销售订单创建成功流程验证",
                "需求ID": "1001",
                "前置条件": "1. 用户已登录ERP系统并拥有订单权限\n2. 系统中存在可用测试商品",
                "用例步骤": "1. 进入销售订单页面\n2. 点击新建订单按钮\n3. 选择测试商品并提交订单",
                "预期结果": "1. 页面打开并显示新建订单按钮\n2. 订单提交成功并生成订单号",
                "用例类型": "功能测试",
                "用例状态": "正常",
                "用例等级": "高",
                "创建人": "余小龙",
                "优先级": "P1",
                "是否可自动化": "是",
                "回归测试标识": "否",
                "知识库关联": "销售订单 客户 商品 库存 数量 价格 权限 状态 提交 校验 业务规则",
                "质量评分": 95,
                "execution_count": 20,
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
