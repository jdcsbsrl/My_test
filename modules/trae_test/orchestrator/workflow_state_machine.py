"""工作流状态机 - 支持审核状态与超时处理"""

from collections.abc import Callable
from datetime import datetime
from enum import Enum


class WorkflowState(Enum):
    """工作流状态枚举"""

    # 初始状态
    PENDING = "pending"  # 待启动

    # 执行状态
    RUNNING = "running"  # 执行中
    GENERATED = "generated"  # 用例已生成

    # 审核状态（新增）
    AWAITING_REVIEW = "awaiting_review"  # 待审核
    REVIEWING = "reviewing"  # 审核中

    # 自动化方案状态
    AUTO_SOLUTION_GENERATED = "auto_solution_generated"  # 自动化方案已生成
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 待用户确认

    # 完成状态
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class Transition:
    """状态转换定义"""

    def __init__(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
        condition: Callable | None = None,
        action: Callable | None = None,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition or (lambda *args, **kwargs: True)
        self.action = action or (lambda *args, **kwargs: None)


class WorkflowStateMachine:
    """工作流状态机"""

    def __init__(self):
        self.transitions = self._build_transitions()
        self.timeout_handlers = {}
        self._register_timeout_handlers()

    def _build_transitions(self) -> list[Transition]:
        """构建状态转换规则"""
        transitions = [
            # 初始启动
            Transition(WorkflowState.PENDING, WorkflowState.RUNNING),
            # 用例生成完成
            Transition(WorkflowState.RUNNING, WorkflowState.GENERATED),
            # 进入审核
            Transition(WorkflowState.GENERATED, WorkflowState.AWAITING_REVIEW),
            # 审核中
            Transition(WorkflowState.AWAITING_REVIEW, WorkflowState.REVIEWING),
            # 审核通过
            Transition(
                WorkflowState.REVIEWING, WorkflowState.AUTO_SOLUTION_GENERATED, condition=self._all_cases_approved
            ),
            # 审核驳回（返回编辑）
            Transition(WorkflowState.REVIEWING, WorkflowState.GENERATED, condition=self._has_rejected_cases),
            # 自动化方案生成完成
            Transition(WorkflowState.AUTO_SOLUTION_GENERATED, WorkflowState.AWAITING_CONFIRMATION),
            # 用户确认同意
            Transition(WorkflowState.AWAITING_CONFIRMATION, WorkflowState.RUNNING, action=self._on_user_confirm),
            # 用户拒绝（返回方案修改）
            Transition(
                WorkflowState.AWAITING_CONFIRMATION, WorkflowState.AUTO_SOLUTION_GENERATED, action=self._on_user_reject
            ),
            # 完成
            Transition(WorkflowState.RUNNING, WorkflowState.COMPLETED),
            # 失败
            Transition(WorkflowState.RUNNING, WorkflowState.FAILED),
            # 取消
            Transition(WorkflowState.PENDING, WorkflowState.CANCELLED),
            Transition(WorkflowState.RUNNING, WorkflowState.CANCELLED),
        ]
        return transitions

    def _register_timeout_handlers(self):
        """注册超时处理函数"""
        self.timeout_handlers[WorkflowState.AWAITING_REVIEW] = {
            "timeout": 48 * 3600,  # 48小时
            "handler": self._handle_review_timeout,
        }
        self.timeout_handlers[WorkflowState.AWAITING_CONFIRMATION] = {
            "timeout": 24 * 3600,  # 24小时
            "handler": self._handle_confirmation_timeout,
        }

    def _all_cases_approved(self, workflow) -> bool:
        """检查所有用例是否都已通过审核"""
        for step in workflow.steps:
            # 兼容字典和对象两种类型
            result = step.get("result") if isinstance(step, dict) else getattr(step, "result", None)
            if result and isinstance(result, list):
                for case in result:
                    if case.get("审核状态") != "APPROVED":
                        return False
        return True

    def _has_rejected_cases(self, workflow) -> bool:
        """检查是否有驳回的用例"""
        for step in workflow.steps:
            # 兼容字典和对象两种类型
            result = step.get("result") if isinstance(step, dict) else getattr(step, "result", None)
            if result and isinstance(result, list):
                for case in result:
                    if case.get("审核状态") == "REJECTED":
                        return True
        return False

    def _on_user_confirm(self, workflow):
        """用户确认后的处理"""
        workflow.confirmed_at = datetime.now()
        workflow.confirmation_status = "approved"

    def _on_user_reject(self, workflow):
        """用户拒绝后的处理"""
        workflow.confirmation_status = "rejected"

    def _handle_review_timeout(self, workflow):
        """审核超时处理"""
        print(f"[WorkflowStateMachine] 工作流 {workflow.workflow_id} 审核超时，发送提醒通知")
        # 发送提醒通知逻辑（可扩展为邮件、消息通知等）
        workflow.timeout_count = workflow.timeout_count + 1 if hasattr(workflow, "timeout_count") else 1

    def _handle_confirmation_timeout(self, workflow):
        """确认超时处理"""
        print(f"[WorkflowStateMachine] 工作流 {workflow.workflow_id} 确认超时")
        workflow.timeout_count = workflow.timeout_count + 1 if hasattr(workflow, "timeout_count") else 1

    def can_transition(self, workflow, target_state: WorkflowState) -> bool:
        """检查是否可以转换到目标状态"""
        current_state = self._get_workflow_state(workflow)

        for transition in self.transitions:
            if transition.from_state == current_state and transition.to_state == target_state:
                return transition.condition(workflow)

        return False

    def transition(self, workflow, target_state: WorkflowState) -> bool:
        """执行状态转换"""
        if not self.can_transition(workflow, target_state):
            return False

        current_state = self._get_workflow_state(workflow)

        for transition in self.transitions:
            if transition.from_state == current_state and transition.to_state == target_state:
                # 执行转换动作
                transition.action(workflow)

                # 更新工作流状态
                workflow.state = target_state.value
                workflow.last_state_change = datetime.now()

                # 启动超时监控（如果目标状态有超时设置）
                if target_state in self.timeout_handlers:
                    self._start_timeout_monitor(workflow, target_state)

                print(
                    f"[WorkflowStateMachine] 工作流 {workflow.workflow_id} 状态变更: {current_state.value} -> {target_state.value}"
                )
                return True

        return False

    def _get_workflow_state(self, workflow) -> WorkflowState:
        """获取工作流当前状态"""
        state_value = getattr(workflow, "state", WorkflowState.PENDING.value)
        try:
            return WorkflowState(state_value)
        except ValueError:
            return WorkflowState.PENDING

    def _start_timeout_monitor(self, workflow, state: WorkflowState):
        """启动超时监控"""
        timeout_config = self.timeout_handlers.get(state)
        if timeout_config:
            # 记录超时开始时间
            workflow.timeout_start = datetime.now()
            workflow.timeout_state = state.value
            print(
                f"[WorkflowStateMachine] 启动超时监控: {state.value}, 超时时间: {timeout_config['timeout']/3600:.1f}小时"
            )

    def check_timeouts(self):
        """检查所有工作流的超时状态"""
        now = datetime.now()
        for workflow in self._get_all_workflows():
            if hasattr(workflow, "timeout_start") and hasattr(workflow, "timeout_state"):
                try:
                    state = WorkflowState(workflow.timeout_state)
                    timeout_config = self.timeout_handlers.get(state)

                    if timeout_config:
                        elapsed = (now - workflow.timeout_start).total_seconds()
                        if elapsed >= timeout_config["timeout"]:
                            timeout_config["handler"](workflow)
                            # 重置超时标记
                            delattr(workflow, "timeout_start")
                            delattr(workflow, "timeout_state")
                except ValueError:
                    pass

    def _get_all_workflows(self):
        """获取所有工作流（需要在实际使用时注入）"""
        return []

    def apply_audit_result(self, current_state: WorkflowState, audit_result) -> tuple[WorkflowState, list[str]]:
        """根据 AuditResult 驱动状态转换

        延迟导入 AuditResult, AuditIssue 避免循环依赖。

        Args:
            current_state: 当前状态
            audit_result: 审核结果

        Returns:
            tuple[WorkflowState, list[str]]: (新状态, 转换消息列表)
        """

        messages = []

        # 检查是否有 manual_review 级别的问题
        has_manual_review = any(
            issue.severity == "manual_review" for issue in audit_result.issues
        )

        # 检查是否通过
        if audit_result.passed:
            if current_state in (WorkflowState.AWAITING_REVIEW, WorkflowState.REVIEWING):
                new_state = self._find_next_after_review(current_state)
                messages.append("审核通过，状态推进")
                return (new_state, messages)
            return (current_state, messages)

        # 有 manual_review 问题 → 待人工审核
        if has_manual_review:
            messages.append(
                f"发现 {sum(1 for i in audit_result.issues if i.severity == 'manual_review')} 个待人工确认问题"
            )
            return (WorkflowState.AWAITING_REVIEW, messages)

        # 审核未通过且有 error → 失败
        messages.append(f"审核未通过：{len(audit_result.errors)} 个错误")
        return (WorkflowState.FAILED, messages)

    def _find_next_after_review(self, current: WorkflowState) -> WorkflowState:
        """查找审核通过后的下一个状态"""
        review_transitions = {
            WorkflowState.AWAITING_REVIEW: WorkflowState.REVIEWING,
            WorkflowState.REVIEWING: WorkflowState.COMPLETED,
        }
        return review_transitions.get(current, WorkflowState.COMPLETED)

    def get_available_transitions(self, workflow) -> list[WorkflowState]:
        """获取当前状态可转换到的目标状态"""
        current_state = self._get_workflow_state(workflow)
        available = []

        for transition in self.transitions:
            if transition.from_state == current_state and transition.condition(workflow):
                available.append(transition.to_state)

        return available


class StateLockManager:
    """状态锁定管理器"""

    def __init__(self):
        self.locked_workflows = {}  # workflow_id -> lock_info

    def lock(self, workflow_id: str, lock_reason: str = "") -> bool:
        """锁定工作流，防止状态变更"""
        if workflow_id in self.locked_workflows:
            return False

        self.locked_workflows[workflow_id] = {
            "locked_at": datetime.now(),
            "lock_reason": lock_reason,
            "locked_by": "system",
        }
        print(f"[StateLockManager] 工作流 {workflow_id} 已锁定: {lock_reason}")
        return True

    def unlock(self, workflow_id: str) -> bool:
        """解锁工作流"""
        if workflow_id not in self.locked_workflows:
            return False

        del self.locked_workflows[workflow_id]
        print(f"[StateLockManager] 工作流 {workflow_id} 已解锁")
        return True

    def is_locked(self, workflow_id: str) -> bool:
        """检查工作流是否被锁定"""
        return workflow_id in self.locked_workflows

    def get_lock_info(self, workflow_id: str) -> dict | None:
        """获取锁定信息"""
        return self.locked_workflows.get(workflow_id)

    def auto_lock_on_review(self, workflow):
        """在审核状态自动锁定工作流"""
        if getattr(workflow, "state", "") == WorkflowState.AWAITING_REVIEW.value:
            self.lock(workflow.workflow_id, "等待审核中")

    def auto_unlock_on_approval(self, workflow):
        """审核通过后自动解锁"""
        if getattr(workflow, "state", "") == WorkflowState.AUTO_SOLUTION_GENERATED.value:
            self.unlock(workflow.workflow_id)


# 全局状态机实例
state_machine = WorkflowStateMachine()
lock_manager = StateLockManager()


if __name__ == "__main__":
    # 测试状态机
    class MockWorkflow:
        def __init__(self):
            self.workflow_id = "test_wf_001"
            self.state = WorkflowState.PENDING.value
            self.steps = []
            self.last_state_change = None
            self.timeout_count = 0

    wf = MockWorkflow()

    # 测试状态转换
    print("初始状态:", wf.state)

    state_machine.transition(wf, WorkflowState.RUNNING)
    print("转换后状态:", wf.state)

    state_machine.transition(wf, WorkflowState.GENERATED)
    print("转换后状态:", wf.state)

    state_machine.transition(wf, WorkflowState.AWAITING_REVIEW)
    print("转换后状态:", wf.state)

    # 测试锁定
    lock_manager.auto_lock_on_review(wf)
    print("是否锁定:", lock_manager.is_locked(wf.workflow_id))

    # 测试可用转换
    available = state_machine.get_available_transitions(wf)
    print("可用转换:", [s.value for s in available])
