"""工作流管理器 - 多Agent协同工作系统

提供：
- WorkflowStep: 工作流步骤定义
- Workflow: 工作流定义和执行
- WorkflowManager: 工作流管理器
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from .audit_agent_enhanced import AuditAgent, AuditFailedException, AuditResult
from .config import AuditType, WorkflowConfig
from .exception_handler import WorkflowExecutionException


class StepStatus(Enum):
    """步骤状态枚举"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    AUDITING = "auditing"  # 正在审核
    PASSED = "passed"  # 审核通过
    FAILED = "failed"  # 审核失败
    RETRYING = "retrying"  # 正在重试
    SKIPPED = "skipped"  # 已跳过
    BLOCKED = "blocked"  # 被阻断


class StepType(Enum):
    """步骤类型枚举"""

    AGENT = "agent"  # Agent执行
    AUDIT = "audit"  # 审核
    EXPORT = "export"  # 导出
    VALIDATE = "validate"  # 验证
    CUSTOM = "custom"  # 自定义


class WorkflowStatus(Enum):
    """工作流状态枚举"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 已失败


@dataclass
class WorkflowStep:
    """工作流步骤"""

    # 步骤唯一标识
    step_id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")

    # 步骤名称
    name: str = ""

    # 步骤类型
    step_type: StepType = StepType.AGENT

    # 执行的Agent类型
    agent_type: str = ""

    # 步骤执行函数
    execute_func: Callable | None = None

    # 审核类型（如果是审核步骤）
    audit_type: AuditType = AuditType.ALL

    # 依赖的步骤ID列表
    depends_on: list[str] = field(default_factory=list)

    # 步骤参数
    params: dict[str, Any] = field(default_factory=dict)

    # 状态
    status: StepStatus = StepStatus.PENDING

    # 执行结果
    result: Any = None

    # 审核结果
    audit_result: AuditResult | None = None

    # 执行时间
    start_time: datetime | None = None
    end_time: datetime | None = None

    # 重试次数
    retry_count: int = 0

    # 最大重试次数
    max_retries: int = 3

    # 是否必需（必需步骤失败会导致整个工作流失败）
    required: bool = True

    # 步骤描述
    description: str = ""

    def get_execution_time(self) -> float:
        """获取执行时间（秒）"""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now(UTC)
        return (end - self.start_time).total_seconds()

    def can_execute(self, completed_steps: dict[str, "WorkflowStep"]) -> bool:
        """检查是否可以执行

        Args:
            completed_steps: 已完成的步骤字典

        Returns:
            bool: 是否可以执行
        """
        if self.status != StepStatus.PENDING:
            return False

        # 检查依赖
        for dep_id in self.depends_on:
            dep_step = completed_steps.get(dep_id)
            if not dep_step:
                return False
            if dep_step.status not in [StepStatus.PASSED, StepStatus.SKIPPED]:
                return False

        return True


@dataclass
class Workflow:
    """工作流"""

    # 工作流唯一标识
    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:8]}")

    # 工作流名称
    name: str = ""

    # 工作流描述
    description: str = ""

    # 步骤列表
    steps: list[WorkflowStep] = field(default_factory=list)

    # 工作流配置
    config: WorkflowConfig = field(default_factory=WorkflowConfig)

    # 创建时间
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # 开始时间
    start_time: datetime | None = None

    # 结束时间
    end_time: datetime | None = None

    # 当前步骤索引
    current_step_index: int = 0

    # 工作流状态（枚举，替代原来的三个布尔值）
    status: WorkflowStatus = WorkflowStatus.PENDING

    # 错误信息
    error_message: str = ""

    def add_step(self, step: WorkflowStep) -> Workflow:
        """添加步骤

        Args:
            step: 工作流步骤

        Returns:
            Workflow: 返回自身，支持链式调用
        """
        self.steps.append(step)
        return self

    def get_step(self, step_id: str) -> WorkflowStep | None:
        """获取步骤

        Args:
            step_id: 步骤ID

        Returns:
            WorkflowStep: 步骤对象，如果不存在返回None
        """
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_execution_time(self) -> float:
        """获取总执行时间（秒）"""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now(UTC)
        return (end - self.start_time).total_seconds()

    def get_summary(self) -> dict[str, Any]:
        """获取工作流摘要

        Returns:
            Dict: 工作流摘要信息
        """
        total_steps = len(self.steps)
        passed = sum(1 for s in self.steps if s.status == StepStatus.PASSED)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)

        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "total_steps": total_steps,
            "passed": passed,
            "failed": failed,
            "skipped": sum(1 for s in self.steps if s.status == StepStatus.SKIPPED),
            "execution_time": self.get_execution_time(),
            "is_running": self.status == WorkflowStatus.RUNNING,
            "is_completed": self.status == WorkflowStatus.COMPLETED,
            "is_failed": self.status == WorkflowStatus.FAILED,
        }


class WorkflowManager:
    """工作流管理器"""

    def __init__(self, config: WorkflowConfig = None):
        """初始化工作流管理器

        Args:
            config: 工作流配置
        """
        self.config = config or WorkflowConfig()
        self.workflows: dict[str, Workflow] = {}
        self._lock = threading.Lock()

    def create_workflow(self, name: str, description: str = "", steps: list[WorkflowStep] = None) -> Workflow:
        """创建工作流

        Args:
            name: 工作流名称
            description: 工作流描述
            steps: 步骤列表

        Returns:
            Workflow: 创建的工作流
        """
        workflow = Workflow(name=name, description=description, config=self.config)

        if steps:
            for step in steps:
                workflow.add_step(step)

        with self._lock:
            self.workflows[workflow.workflow_id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """获取工作流

        Args:
            workflow_id: 工作流ID

        Returns:
            Workflow: 工作流对象，如果不存在返回None
        """
        with self._lock:
            return self.workflows.get(workflow_id)

    def execute_workflow(
        self,
        workflow_id: str,
        executor: Callable[[WorkflowStep, Any], Any],
        auditor: AuditAgent,
        on_step_start: Callable[[WorkflowStep], None] | None = None,
        on_step_complete: Callable[[WorkflowStep], None] | None = None,
        on_audit_fail: Callable[[WorkflowStep, AuditResult], None] | None = None,
        input_data: Any = None,
    ) -> Workflow:
        """执行工作流

        Args:
            workflow_id: 工作流ID
            executor: 步骤执行器
            auditor: 审核Agent
            on_step_start: 步骤开始回调
            on_step_complete: 步骤完成回调
            on_audit_fail: 审核失败回调
            input_data: 输入数据

        Returns:
            Workflow: 执行完成的工作流

        Raises:
            WorkflowExecutionException: 工作流执行失败
        """
        with self._lock:
            workflow = self.workflows.get(workflow_id)
            if not workflow:
                raise WorkflowExecutionException(f"工作流不存在: {workflow_id}")

            if workflow.status == WorkflowStatus.RUNNING:
                raise WorkflowExecutionException(f"工作流正在执行中: {workflow_id}")

            # 重置所有步骤状态（支持重新执行）
            for step in workflow.steps:
                step.status = StepStatus.PENDING
                step.result = None
                step.audit_result = None
                step.start_time = None
                step.end_time = None
                step.retry_count = 0

            # 重置工作流状态
            workflow.error_message = ""
            workflow.current_step_index = 0
            workflow.end_time = None

            # 标记工作流开始
            workflow.start_time = datetime.now(UTC)
            workflow.status = WorkflowStatus.RUNNING

        try:
            # 拓扑排序确定执行顺序（解决依赖顺序问题）
            sorted_steps = self._topological_sort(workflow)

            # 按顺序执行步骤
            completed_steps: dict[str, WorkflowStep] = {}

            # 保存前一个步骤的结果，用于传递给下一个步骤
            previous_result = input_data

            for i, step in enumerate(sorted_steps):
                # 检查是否可以执行（防御性校验，防止循环依赖）
                if not step.can_execute(completed_steps):
                    # 标记为被阻断
                    step.status = StepStatus.BLOCKED
                    print(f"⏭️ 跳过步骤: {step.name} (依赖未就绪)")
                    continue

                # 执行步骤
                workflow.current_step_index = i

                # 内层重试循环
                step_failed_required = False
                for attempt in range(step.max_retries + 1):
                    if attempt == 0:
                        step.start_time = datetime.now(UTC)
                    step.status = StepStatus.RUNNING

                    print(f"\n🚀 开始执行: {step.name} (尝试 {attempt + 1}/{step.max_retries + 1})")
                    print(f"   类型: {step.step_type.value}")

                    if attempt == 0 and on_step_start:
                        on_step_start(step)

                    try:
                        # 根据步骤类型决定执行方式
                        if step.step_type == StepType.AUDIT:
                            # 审计类型步骤：直接审核前一步结果，不更新 previous_result
                            step.result = previous_result
                            print("  📋 审计步骤，直接审核上一步结果")
                        else:
                            # 执行步骤
                            step.result = executor(step, previous_result)

                        # 更新前一个步骤的结果，供下一个步骤使用（审计步骤不传递）
                        if step.result is not None and step.step_type != StepType.AUDIT:
                            previous_result = step.result

                        # 审核步骤结果
                        print(f"🔍 开始审核: {step.name} (审核类型: {step.audit_type.value})")
                        step.status = StepStatus.AUDITING

                        try:
                            audit_result = auditor.audit(
                                target=step.result,
                                audit_type=step.audit_type,
                                context={"step": step, "workflow": workflow},
                            )
                        except AuditFailedException:
                            print(f"⛔ 硬阻断触发: {step.name}")
                            raise

                        step.audit_result = audit_result

                        if audit_result.passed:
                            # 审核通过
                            step.status = StepStatus.PASSED
                            step.end_time = datetime.now(UTC)

                            print(f"✅ 审核通过: {step.name}")

                            if audit_result.warnings:
                                print(f"⚠️ 有 {len(audit_result.warnings)} 个警告:")
                                for warning in audit_result.warnings:
                                    print(f"   - {warning['message']}")

                            if audit_result.suggestions:
                                print(f"💡 有 {len(audit_result.suggestions)} 个建议:")
                                for suggestion in audit_result.suggestions:
                                    print(f"   - {suggestion}")

                            if on_step_complete:
                                on_step_complete(step)

                            # 记录已完成步骤
                            completed_steps[step.step_id] = step
                            break  # 退出重试循环，步骤成功

                        # 审核失败
                        print(f"❌ 审核失败: {step.name}")
                        print(f"   错误数量: {len(audit_result.errors)}")
                        for error in audit_result.errors:
                            print(f"   - [{error['code']}] {error['message']}")
                            if error.get("location"):
                                print(f"     位置: {error['location']}")

                        if attempt < step.max_retries:
                            # 重试
                            step.status = StepStatus.RETRYING
                            step.retry_count += 1
                            print(f"🔄 将尝试重试 ({step.retry_count}/{step.max_retries})")
                            continue
                        else:
                            # 超过最大重试次数
                            step.status = StepStatus.FAILED
                            step.end_time = datetime.now(UTC)

                            if on_audit_fail:
                                on_audit_fail(step, audit_result)

                            if step.required:
                                step_failed_required = True
                                print("💥 必需步骤审核失败，工作流终止")
                            else:
                                step.status = StepStatus.SKIPPED
                                completed_steps[step.step_id] = step
                                print("⏭️ 非必需步骤审核失败，已跳过")
                            break  # 退出重试循环

                    except AuditFailedException:
                        raise  # 硬阻断，向上传播

                    except Exception as e:
                        print(f"💥 步骤执行异常: {step.name}")
                        print(f"   错误: {str(e)}")

                        if attempt < step.max_retries:
                            # 重试
                            step.status = StepStatus.RETRYING
                            step.retry_count += 1
                            print(f"🔄 步骤执行异常，将尝试重试 ({step.retry_count}/{step.max_retries})")
                            continue
                        else:
                            step.status = StepStatus.FAILED
                            step.end_time = datetime.now(UTC)

                            if step.required:
                                step_failed_required = True
                                workflow.error_message = f"步骤执行失败: {step.name}, 错误: {str(e)}"
                                print("💥 必需步骤异常，工作流终止")
                            else:
                                step.status = StepStatus.SKIPPED
                                completed_steps[step.step_id] = step
                                print("⏭️ 非必需步骤异常，已跳过")
                            break  # 退出重试循环

                # 重试循环结束后，必需步骤失败则终止整个工作流
                if step_failed_required:
                    workflow.status = WorkflowStatus.FAILED
                    if not workflow.error_message:
                        workflow.error_message = f"必需步骤失败: {step.name}"
                    break

            # 标记工作流完成
            workflow.end_time = datetime.now(UTC)
            if workflow.status != WorkflowStatus.FAILED:
                workflow.status = WorkflowStatus.COMPLETED

        except Exception as e:
            workflow.end_time = datetime.now(UTC)
            workflow.status = WorkflowStatus.FAILED
            workflow.error_message = f"工作流执行异常: {str(e)}"
            raise

        return workflow

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """获取工作流状态

        Args:
            workflow_id: 工作流ID

        Returns:
            Dict: 工作流状态信息
        """
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return None

        return workflow.get_summary()

    def list_workflows(self) -> list[dict[str, Any]]:
        """列出所有工作流

        Returns:
            List[Dict]: 工作流摘要列表
        """
        with self._lock:
            workflows_copy = list(self.workflows.values())
        return [wf.get_summary() for wf in workflows_copy]

    def cleanup_completed_workflows(self, max_age_hours: int = 24):
        """清理已完成的工作流

        Args:
            max_age_hours: 最大保留时间（小时）
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=max_age_hours)

        with self._lock:
            to_remove = [wf_id for wf_id, wf in self.workflows.items() if wf.end_time and wf.end_time < cutoff_time]
            for wf_id in to_remove:
                if wf_id in self.workflows:
                    del self.workflows[wf_id]

    @staticmethod
    def _topological_sort(workflow: Workflow) -> list[WorkflowStep]:
        """拓扑排序确定步骤执行顺序（Kahn算法）

        解决 depends_on 依赖在顺序遍历中失效的问题。
        如果存在循环依赖，环内步骤会被标记为 BLOCKED。

        Args:
            workflow: 工作流对象

        Returns:
            list[WorkflowStep]: 排序后的步骤列表
        """
        from collections import deque

        step_map = {s.step_id: s for s in workflow.steps}
        in_degree = {s.step_id: 0 for s in workflow.steps}
        adjacency = {s.step_id: [] for s in workflow.steps}

        # 构建依赖图
        for s in workflow.steps:
            for dep_id in s.depends_on:
                if dep_id in step_map:
                    adjacency[dep_id].append(s.step_id)
                    in_degree[s.step_id] += 1

        # Kahn算法拓扑排序
        queue = deque([sid for sid, deg in in_degree.items() if deg == 0])
        sorted_steps: list[WorkflowStep] = []

        while queue:
            sid = queue.popleft()
            sorted_steps.append(step_map[sid])
            for next_sid in adjacency[sid]:
                in_degree[next_sid] -= 1
                if in_degree[next_sid] == 0:
                    queue.append(next_sid)

        # 检测环：环内步骤标记为 BLOCKED
        if len(sorted_steps) != len(workflow.steps):
            sorted_ids = {s.step_id for s in sorted_steps}
            for s in workflow.steps:
                if s.step_id not in sorted_ids:
                    s.status = StepStatus.BLOCKED
                    print(f"⏭️ 检测到依赖环: {s.name}")

        return sorted_steps
