"""配置类 - 多Agent协同工作系统配置

定义所有配置类，包括：
- OrchestratorConfig: 编排器配置
- AuditConfig: 审核配置
- RetryConfig: 重试配置
- WorkflowConfig: 工作流配置
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class AuditType(Enum):
    """审核类型枚举"""

    TEST_CASE = "test_case"  # 测试用例审核
    CODE = "code"  # 代码规范审核
    ENVIRONMENT = "environment"  # 环境审核
    IMPACT = "impact"  # 影响分析
    SECURITY = "security"  # 安全审核
    ALL = "all"  # 全能审核


class OutputMode(Enum):
    """输出模式枚举"""

    CONSOLE = "console"  # 仅控制台
    REPORT = "report"  # 仅报告
    BOTH = "both"  # 两者都要


@dataclass
class AuditConfig:
    """审核配置"""

    # 是否启用硬阻断
    enforce_hard_block: bool = True

    # 是否启用审核
    enabled: bool = True

    # 审核严格程度 (1-5, 5最严格)
    strict_level: int = 3

    # 是否记录详细日志
    detailed_logging: bool = True

    # 审核超时时间（秒）
    timeout: int = 30

    # 审核类型列表
    audit_types: list[AuditType] = field(
        default_factory=lambda: [
            AuditType.TEST_CASE,
            AuditType.CODE,
            AuditType.ENVIRONMENT,
            AuditType.IMPACT,
            AuditType.SECURITY,
        ]
    )

    # 是否自动选择审核类型
    auto_select_audit_types: bool = True

    # 交互审批模式：True=等待用户输入确认，False=由 auto_approve 决定后续行为
    interactive_mode: bool = True

    # 非交互模式下是否自动批准（仅在 interactive_mode=False 且非 CI 环境时生效）
    auto_approve: bool = False

    def __post_init__(self):
        """后处理"""
        # 如果audit_types是字符串列表，转换为枚举
        if self.audit_types and isinstance(self.audit_types[0], str):
            self.audit_types = [AuditType(at) for at in self.audit_types]


@dataclass
class RetryConfig:
    """重试配置"""

    # 最大重试次数
    max_retries: int = 3

    # 基础延迟时间（秒）
    base_delay: float = 1.0

    # 是否使用指数退避
    exponential_backoff: bool = True

    # 最大延迟时间（秒）
    max_delay: float = 30.0

    # 是否启用重试
    enabled: bool = True

    # 重试的最大时间（秒），超过则不再重试
    max_total_time: float = 300.0

    def calculate_delay(self, attempt: int) -> float:
        """计算延迟时间

        Args:
            attempt: 当前尝试次数（从1开始）

        Returns:
            float: 延迟时间（秒）
        """
        if not self.exponential_backoff:
            return self.base_delay

        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)


@dataclass
class WorkflowConfig:
    """工作流配置"""

    # 工作流名称
    name: str = "default"

    # 是否启用并行执行
    enable_parallel: bool = True

    # 最大并行任务数
    max_parallel_tasks: int = 3

    # 是否记录执行时间
    record_execution_time: bool = True

    # 是否生成报告
    generate_report: bool = True

    # 报告输出路径
    report_path: str | None = None

    # 是否启用断点续传
    enable_resume: bool = True

    # 是否在出错时立即停止
    stop_on_error: bool = True


@dataclass
class OrchestratorConfig:
    """编排器配置"""

    # 审核配置
    audit_config: AuditConfig = field(default_factory=AuditConfig)

    # 重试配置
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    # 工作流配置
    workflow_config: WorkflowConfig = field(default_factory=WorkflowConfig)

    # 输出模式
    output_mode: OutputMode = OutputMode.BOTH

    # 是否启用调试模式
    debug_mode: bool = False

    # 通知回调函数（可选）
    notify_callback: Callable | None = None

    # 用户ID（用于通知）
    user_id: str | None = None

    # 项目ID（用于隔离）
    project_id: str | None = None

    # 工作空间路径
    workspace_path: str = r"D:\Working\test_erp\workspace"

    # 临时文件路径
    temp_path: str = r"D:\Working\test_erp\temp"

    def __post_init__(self):
        """后处理"""
        # 如果notify_callback是字符串，尝试转换为函数
        if isinstance(self.notify_callback, str) and self.notify_callback == "print":
            self.notify_callback = print
