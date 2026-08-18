"""自动化测试前置审核

在自动化测试执行前进行审核，确保：
1. UAT 环境合规性
2. 测试用例准备就绪
3. 审核通过后才允许执行真实测试
"""

import logging

from modules.trae_test.orchestrator.audit_gateway import AuditGateway
from modules.trae_test.orchestrator.audit_models import AuditResult

logger = logging.getLogger(__name__)


class PreAudit:
    """自动化测试前置审核"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.gateway = AuditGateway()

    def check_environment(self, env_config: dict) -> AuditResult:
        """审核测试环境

        检查：
        - 环境是否为 UAT 测试环境
        - 环境配置是否完整
        - 依赖服务是否可达
        """
        context = {
            "source": "auto_test_pre_audit",
            "block_on_fail": True,
        }
        return self.gateway.audit(env_config, "environment", context)

    def check_test_readiness(self, test_plan: dict) -> AuditResult:
        """审核测试就绪状态

        检查：
        - 测试用例是否已准备
        - 测试数据是否已准备
        - 测试账号是否可用
        """
        from modules.trae_test.orchestrator.audit_models import AuditIssue

        context = {
            "source": "auto_test_pre_audit",
            "block_on_fail": False,
        }

        if isinstance(test_plan, dict):
            result = AuditResult()

            required_keys = ["test_cases", "test_data", "test_account"]
            missing_keys = [k for k in required_keys if k not in test_plan]

            if missing_keys:
                for key in missing_keys:
                    result.issues.append(
                        AuditIssue(
                            severity="warning",
                            rule_id=f"READINESS_MISSING_{key.upper()}",
                            category="readiness",
                            message=f"测试计划缺少必需字段: {key}",
                        )
                    )

            test_cases = test_plan.get("test_cases", [])
            if not isinstance(test_cases, list) or len(test_cases) == 0:
                result.issues.append(
                    AuditIssue(
                        severity="warning",
                        rule_id="READINESS_NO_TEST_CASES",
                        category="readiness",
                        message="测试计划中没有测试用例",
                    )
                )

            return result

        return self.gateway.audit(test_plan, "test_case", context)

    def pre_audit(self, env_config: dict, test_plan: dict | None = None) -> bool:
        """执行完整前置审核

        所有审核通过才允许执行测试。

        Returns:
            bool: 是否允许执行测试
        """
        # 1. 环境审核
        env_result = self.check_environment(env_config)
        if not env_result.passed:
            logger.error(f"环境审核未通过，测试已阻止: {env_result.errors}")
            return False

        # 2. 测试就绪审核（如果有测试计划）
        if test_plan:
            readiness_result = self.check_test_readiness(test_plan)
            if not readiness_result.passed:
                logger.warning(f"测试就绪审核有警告: {readiness_result.warnings}")

        logger.info("前置审核全部通过，允许执行测试")
        return True
