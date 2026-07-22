"""监控和报告系统 - 多Agent协同工作系统

提供：
- WorkflowMonitor: 工作流执行监控
- WorkflowReporter: 工作流报告生成
"""

import sys
from datetime import datetime
from enum import Enum
from typing import Any

from .config import OutputMode
from .workflow_manager import StepStatus, Workflow, WorkflowStatus, WorkflowStep


class LogLevel(Enum):
    """日志级别"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


class ConsoleColors:
    """控制台颜色"""

    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


class WorkflowMonitor:
    """工作流监控器

    提供实时控制台输出和工作流状态监控。
    """

    def __init__(self, output_mode: OutputMode = OutputMode.BOTH):
        """初始化监控器

        Args:
            output_mode: 输出模式
        """
        self.output_mode = output_mode
        self.logs: list[dict[str, Any]] = []
        self.start_time = datetime.now()
        self.enable_colors = sys.stdout.isatty()

    def log(self, message: str, level: LogLevel = LogLevel.INFO, indent: int = 0):
        """记录日志

        Args:
            message: 日志消息
            level: 日志级别
            indent: 缩进级别
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        indent_str = "  " * indent

        log_entry = {"timestamp": timestamp, "level": level.value, "message": message, "datetime": datetime.now()}

        self.logs.append(log_entry)

        if self.output_mode in [OutputMode.CONSOLE, OutputMode.BOTH]:
            self._print_to_console(timestamp, level, indent_str, message)

    def _print_to_console(self, timestamp: str, level: LogLevel, indent: str, message: str):
        """打印到控制台

        Args:
            timestamp: 时间戳
            level: 日志级别
            indent: 缩进
            message: 消息
        """
        if self.enable_colors:
            color = self._get_color(level)
            prefix = f"{ConsoleColors.GRAY}{timestamp}{ConsoleColors.RESET} "
            suffix = ConsoleColors.RESET

            print(f"{prefix}{color}{level.value:8s}{ConsoleColors.RESET} {indent}{color}{message}{suffix}")
        else:
            print(f"[{timestamp}] {level.value:8s} {indent}{message}")

    def _get_color(self, level: LogLevel) -> str:
        """获取日志级别对应的颜色

        Args:
            level: 日志级别

        Returns:
            str: 颜色代码
        """
        colors = {
            LogLevel.DEBUG: ConsoleColors.GRAY,
            LogLevel.INFO: ConsoleColors.WHITE,
            LogLevel.WARNING: ConsoleColors.YELLOW,
            LogLevel.ERROR: ConsoleColors.RED,
            LogLevel.SUCCESS: ConsoleColors.GREEN,
        }
        return colors.get(level, ConsoleColors.WHITE)

    def log_step_start(self, step: WorkflowStep):
        """记录步骤开始

        Args:
            step: 工作流步骤
        """
        self.log(f"📋 步骤开始: {step.name}", LogLevel.INFO, indent=1)
        if step.description:
            self.log(f"   描述: {step.description}", LogLevel.DEBUG, indent=2)

    def log_step_complete(self, step: WorkflowStep):
        """记录步骤完成

        Args:
            step: 工作流步骤
        """
        status = step.status
        status_icon = {
            StepStatus.PASSED: "✅",
            StepStatus.FAILED: "❌",
            StepStatus.SKIPPED: "⏭️",
            StepStatus.RETRYING: "🔄",
        }.get(status, "❓")

        execution_time = step.get_execution_time()

        self.log(
            f"{status_icon} 步骤完成: {step.name} (耗时 {execution_time:.2f}秒)",
            LogLevel.SUCCESS if status == StepStatus.PASSED else LogLevel.ERROR,
            indent=1,
        )

    def log_audit(self, audit_result, audit_type: str):
        """记录审核

        Args:
            audit_result: 审核结果
            audit_type: 审核类型
        """
        if audit_result.passed:
            self.log(f"🔍 审核 [{audit_type}]: ✅ 通过", LogLevel.SUCCESS, indent=2)
        else:
            self.log(f"🔍 审核 [{audit_type}]: ❌ 失败 ({len(audit_result.errors)}个错误)", LogLevel.ERROR, indent=2)

            for i, error in enumerate(audit_result.errors[:3], start=1):
                self.log(f"   {i}. {error['message']}", LogLevel.ERROR, indent=3)

            if len(audit_result.errors) > 3:
                self.log(f"   ... 还有 {len(audit_result.errors) - 3} 个错误", LogLevel.ERROR, indent=3)

    def log_error(self, error: Exception, context: str = ""):
        """记录错误

        Args:
            error: 异常
            context: 上下文信息
        """
        error_msg = f"错误: {str(error)}"
        if context:
            error_msg = f"{context}: {error_msg}"

        self.log(error_msg, LogLevel.ERROR, indent=1)

    def log_progress(self, current: int, total: int, message: str = ""):
        """记录进度

        Args:
            current: 当前进度
            total: 总数
            message: 消息
        """
        percentage = (current / total * 100) if total > 0 else 0
        progress_bar = self._generate_progress_bar(percentage)

        msg = f"{progress_bar} {percentage:5.1f}% ({current}/{total})"
        if message:
            msg += f" - {message}"

        self.log(msg, LogLevel.INFO)

    def _generate_progress_bar(self, percentage: float, width: int = 20) -> str:
        """生成进度条

        Args:
            percentage: 百分比
            width: 进度条宽度

        Returns:
            str: 进度条字符串
        """
        filled = int(width * percentage / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"

    def log_header(self, title: str):
        """记录标题

        Args:
            title: 标题
        """
        line = "=" * 80
        self.log(line, LogLevel.INFO)
        self.log(title.center(80), LogLevel.INFO)
        self.log(line, LogLevel.INFO)

    def log_subheader(self, title: str):
        """记录子标题

        Args:
            title: 标题
        """
        line = "-" * 80
        self.log(line, LogLevel.INFO)
        self.log(title, LogLevel.INFO)
        self.log(line, LogLevel.INFO)

    def get_summary(self) -> dict[str, Any]:
        """获取摘要

        Returns:
            Dict: 摘要信息
        """
        total_time = (datetime.now() - self.start_time).total_seconds()

        return {
            "total_logs": len(self.logs),
            "total_time": total_time,
            "start_time": self.start_time.isoformat(),
            "error_count": sum(1 for log in self.logs if log["level"] == "ERROR"),
            "warning_count": sum(1 for log in self.logs if log["level"] == "WARNING"),
        }


class WorkflowReporter:
    """工作流报告生成器

    生成工作流执行报告。
    """

    def __init__(self, monitor: WorkflowMonitor = None):
        """初始化报告生成器

        Args:
            monitor: 监控器
        """
        self.monitor = monitor or WorkflowMonitor()

    def generate_report(self, workflow: Workflow, include_logs: bool = False) -> str:
        """生成报告

        Args:
            workflow: 工作流
            include_logs: 是否包含日志

        Returns:
            str: 报告文本
        """
        lines = []

        # 标题
        lines.append("=" * 80)
        lines.append("工作流执行报告".center(80))
        lines.append("=" * 80)
        lines.append("")

        # 基本信息
        lines.append("【基本信息】")
        lines.append(f"  工作流ID: {workflow.workflow_id}")
        lines.append(f"  工作流名称: {workflow.name}")
        lines.append(f"  创建时间: {workflow.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  执行时间: {workflow.get_execution_time():.2f}秒")
        lines.append("")

        # 状态
        lines.append("【执行状态】")
        status = (
            "✅ 成功"
            if workflow.status == WorkflowStatus.COMPLETED
            else ("❌ 失败" if workflow.status == WorkflowStatus.FAILED else "⏳ 运行中")
        )
        lines.append(f"  状态: {status}")
        lines.append("")

        # 步骤统计
        lines.append("【步骤统计】")
        total_steps = len(workflow.steps)
        passed_steps = sum(1 for s in workflow.steps if s.status == StepStatus.PASSED)
        failed_steps = sum(1 for s in workflow.steps if s.status == StepStatus.FAILED)

        lines.append(f"  总步骤数: {total_steps}")
        lines.append(f"  成功步骤: {passed_steps}")
        lines.append(f"  失败步骤: {failed_steps}")
        lines.append("")

        # 步骤详情
        lines.append("【步骤详情】")
        for i, step in enumerate(workflow.steps, start=1):
            status_icon = {
                StepStatus.PASSED: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️",
                StepStatus.RUNNING: "🔄",
                StepStatus.PENDING: "⏳",
                StepStatus.RETRYING: "🔄",
            }.get(step.status, "❓")

            lines.append(f"  {i}. {status_icon} {step.name}")
            lines.append(f"     类型: {step.step_type.value}")
            lines.append(f"     耗时: {step.get_execution_time():.2f}秒")
            lines.append(f"     重试: {step.retry_count}次")

            if step.audit_result:
                audit_status = "✅ 通过" if step.audit_result.passed else "❌ 失败"
                lines.append(f"     审核: {audit_status}")

                if not step.audit_result.passed:
                    lines.append(f"     错误: {len(step.audit_result.errors)}个")

            if step.status == StepStatus.FAILED:
                lines.append("     ⚠️ 失败")

            lines.append("")

        # 错误信息
        if workflow.error_message:
            lines.append("【错误信息】")
            lines.append(f"  {workflow.error_message}")
            lines.append("")

        # 日志（可选）
        if include_logs and self.monitor.logs:
            lines.append("【执行日志】")
            for log in self.monitor.logs:
                if log["level"] in ["ERROR", "WARNING"]:
                    lines.append(f"  [{log['timestamp']}] {log['level']}: {log['message']}")
            lines.append("")

        # 摘要
        if self.monitor.logs:
            summary = self.monitor.get_summary()
            lines.append("【监控摘要】")
            lines.append(f"  总日志数: {summary['total_logs']}")
            lines.append(f"  错误数: {summary['error_count']}")
            lines.append(f"  警告数: {summary['warning_count']}")
            lines.append("")

        # 页脚
        lines.append("=" * 80)
        lines.append(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)

        return "\n".join(lines)

    def save_report(self, workflow: Workflow, output_path: str, include_logs: bool = False):
        """保存报告

        Args:
            workflow: 工作流
            output_path: 输出路径
            include_logs: 是否包含日志
        """
        import os

        report = self.generate_report(workflow, include_logs)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"报告已保存: {output_path}")

    def generate_summary_report(self, workflows: list[Workflow]) -> str:
        """生成汇总报告

        Args:
            workflows: 工作流列表

        Returns:
            str: 汇总报告
        """
        lines = []

        lines.append("=" * 80)
        lines.append("工作流汇总报告".center(80))
        lines.append("=" * 80)
        lines.append("")

        lines.append(f"工作流总数: {len(workflows)}")
        lines.append("")

        for i, workflow in enumerate(workflows, start=1):
            status = (
                "✅"
                if workflow.status == WorkflowStatus.COMPLETED
                else ("❌" if workflow.status == WorkflowStatus.FAILED else "⏳")
            )
            lines.append(f"{i}. {status} {workflow.name}")
            lines.append(f"   ID: {workflow.workflow_id}")
            lines.append(f"   耗时: {workflow.get_execution_time():.2f}秒")
            lines.append(f"   步骤: {len(workflow.steps)}")
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)
