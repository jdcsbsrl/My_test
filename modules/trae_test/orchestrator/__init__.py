"""Agent编排器模块 - 多Agent并行协同工作系统

提供：
- Agent编排器：管理多Agent执行顺序和依赖
- 全能审核Agent：实时审核所有输出类型
- 工作流管理器：定义和执行工作流
- 重试管理器：可配置重试机制
- 监控和报告：实时输出和执行报告
- 异常处理：统一异常管理和用户通知

审核范围（全能审核）：
1. 测试用例审核：格式、字段、命名、路径
2. 代码规范审核：编码规范、代码风格、最佳实践
3. 环境审核：依赖配置、环境变量、权限设置
4. 影响分析：代码变更影响范围、兼容性测试
5. 安全审核：敏感信息、数据保护、合规性
"""

from typing import Optional

from .agent_orchestrator import AgentOrchestrator
from .audit_agent_enhanced import AuditAgent, AuditResult, AuditType
from .config import (
    AuditConfig,
    OrchestratorConfig,
    OutputMode,
    WorkflowConfig,
)
from .config import (
    AuditType as ConfigAuditType,
)
from .config import (
    RetryConfig as ConfigRetryConfig,
)
from .exception_handler import (
    AgentException,
    AuditFailedException,
    CodeAuditException,
    EnvironmentAuditException,
    ExceptionHandler,
    MaxRetriesExceededException,
    SecurityAuditException,
    TestCaseAuditException,
)
from .monitor import WorkflowMonitor, WorkflowReporter
from .retry_manager import RetryConfig, RetryManager
from .workflow_manager import Workflow, WorkflowManager, WorkflowStep

_orchestrator_instance = None


def get_orchestrator(config: OrchestratorConfig | None = None) -> AgentOrchestrator:
    """获取或创建全局编排器实例（惰性加载单例）。

    取代原模块级全局变量 `orchestrator = AgentOrchestrator()`，
    避免导入时立即初始化和测试间状态污染。
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = AgentOrchestrator(config)
    return _orchestrator_instance


__all__ = [
    # Agent编排器
    "AgentOrchestrator",
    # 配置类
    "OrchestratorConfig",
    "AuditConfig",
    "RetryConfig",
    "WorkflowConfig",
    "OutputMode",
    "AuditType",
    # 审核Agent
    "AuditAgent",
    "AuditResult",
    # 工作流管理
    "WorkflowStep",
    "Workflow",
    "WorkflowManager",
    # 重试机制
    "RetryManager",
    # 监控报告
    "WorkflowMonitor",
    "WorkflowReporter",
    # 异常处理
    "AgentException",
    "TestCaseAuditException",
    "CodeAuditException",
    "EnvironmentAuditException",
    "SecurityAuditException",
    "AuditFailedException",
    "MaxRetriesExceededException",
    "ExceptionHandler",
]
