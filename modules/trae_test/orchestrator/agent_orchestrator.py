"""Agent编排器 - 多Agent并行协同工作系统

核心功能：
- 管理多Agent执行顺序和依赖
- 协调Agent之间的工作
- 处理并行和串行执行
- 实现工作流状态管理
- 强制执行审核流程
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """Agent统一接口协议。

    所有通过 AgentRegistry 注册的 Agent 必须实现此协议，
    提供 execute(**kwargs) 方法供编排器调用。
    """

    def execute(self, **kwargs: Any) -> Any:
        """执行Agent任务。

        Args:
            **kwargs: 任务参数

        Returns:
            Any: 执行结果
        """
        ...


from .audit_agent_enhanced import AuditAgent, AuditResult
from .config import AuditType, OrchestratorConfig
from .exception_handler import AgentException, ExceptionHandler
from .monitor import WorkflowMonitor
from .retry_manager import RetryManager
from .workflow_manager import StepType, Workflow, WorkflowManager, WorkflowStep, WorkflowStatus


class AgentRegistry:
    """Agent注册表"""

    def __init__(self):
        self.agents: dict[str, Any] = {}

    def register(self, agent_type: str, agent_instance: Any):
        """注册Agent

        Args:
            agent_type: Agent类型
            agent_instance: Agent实例
        """
        self.agents[agent_type] = agent_instance

    def get(self, agent_type: str) -> Any | None:
        """获取Agent

        Args:
            agent_type: Agent类型

        Returns:
            Agent实例
        """
        return self.agents.get(agent_type)

    def list_agents(self) -> list[str]:
        """列出所有Agent类型

        Returns:
            List[str]: Agent类型列表
        """
        return list(self.agents.keys())


@dataclass
class Task:
    """任务"""

    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    task_type: str = ""
    input_data: Any = None
    output_data: Any = None
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    error: str | None = None


class AgentOrchestrator:
    """Agent编排器

    管理多Agent的执行顺序和依赖关系，
    协调Agent之间的工作，
    实现工作流状态管理。
    """

    def __init__(self, config: OrchestratorConfig = None):
        """初始化Agent编排器

        Args:
            config: 编排器配置
        """
        self.config = config or OrchestratorConfig()
        self.agent_registry = AgentRegistry()
        self.audit_agent = AuditAgent(config=self.config.audit_config, notify_callback=self.config.notify_callback)
        self.workflow_manager = WorkflowManager(config=self.config.workflow_config)
        self.retry_manager = RetryManager(config=self.config.retry_config)
        self.monitor = WorkflowMonitor(output_mode=self.config.output_mode.value)
        self.exception_handler = ExceptionHandler(notify_callback=self.config.notify_callback)

        # 初始化默认Agent
        self._register_default_agents()

    def _register_default_agents(self):
        """注册默认Agent"""
        try:
            from ..utils.test_case_generator import TestCaseGenerator

            self.agent_registry.register("test_case_generator", TestCaseGenerator())
        except ImportError as e:
            logger.warning("Agent test_case_generator 注册失败: %s", e)

        try:
            from ..utils.excel_generator import excel_generator

            self.agent_registry.register("excel_generator", excel_generator)
        except ImportError as e:
            logger.warning("Agent excel_generator 注册失败: %s", e)

    def register_agent(self, agent_type: str, agent_instance: Any):
        """注册Agent

        Args:
            agent_type: Agent类型
            agent_instance: Agent实例
        """
        self.agent_registry.register(agent_type, agent_instance)
        self.monitor.log(f"注册Agent: {agent_type}")

    def execute_workflow(self, workflow_def: dict[str, Any], input_data: Any = None) -> Workflow:
        """执行工作流

        Args:
            workflow_def: 工作流定义
            input_data: 输入数据

        Returns:
            Workflow: 执行完成的工作流
        """
        workflow_id = workflow_def.get("workflow_id", f"wf_{uuid.uuid4().hex[:8]}")
        workflow_name = workflow_def.get("name", "默认工作流")

        self.monitor.log(f"开始执行工作流: {workflow_name} ({workflow_id})")

        # 创建工作流
        workflow = self.workflow_manager.create_workflow(
            name=workflow_name, description=workflow_def.get("description", "")
        )

        # 添加步骤
        steps_def = workflow_def.get("steps", [])
        for i, step_def in enumerate(steps_def):
            step = self._create_step(step_def, i)
            workflow.add_step(step)

        # 执行工作流
        def executor(step: WorkflowStep, previous_result: Any = None) -> Any:
            return self._execute_step(step, previous_result, workflow)

        def on_step_complete(step: WorkflowStep):
            self.monitor.log_step_complete(step)

        def on_audit_fail(step: WorkflowStep, audit_result: AuditResult):
            self.monitor.log(f"步骤审核失败: {step.name}")
            self.monitor.log(f"错误数量: {len(audit_result.errors)}")

            # 通知用户
            if self.config.notify_callback:
                self.exception_handler.notify_user(f"步骤 {step.name} 审核失败", audit_result.to_dict())

        try:
            result_workflow = self.workflow_manager.execute_workflow(
                workflow_id=workflow.workflow_id,
                executor=executor,
                auditor=self.audit_agent,
                on_step_complete=on_step_complete,
                on_audit_fail=on_audit_fail,
                input_data=input_data,
            )

            # 生成报告
            self._generate_workflow_report(result_workflow)

            self.monitor.log(f"工作流执行完成: {workflow_name}")
            return result_workflow

        except Exception as e:
            self.monitor.log(f"工作流执行失败: {str(e)}")
            raise

    def _create_step(self, step_def: dict[str, Any], index: int) -> WorkflowStep:
        """创建工作流步骤

        Args:
            step_def: 步骤定义
            index: 步骤索引

        Returns:
            WorkflowStep: 工作流步骤
        """
        step_type_str = step_def.get("type", "AGENT").upper()
        if step_type_str not in StepType.__members__:
            raise ValueError(f"Invalid step type: {step_type_str}")

        audit_type_str = step_def.get("audit_type", "ALL").upper()
        if audit_type_str not in AuditType.__members__:
            raise ValueError(f"Invalid audit type: {audit_type_str}")

        step = WorkflowStep(
            step_id=step_def.get("step_id", f"step_{index}"),
            name=step_def.get("name", f"步骤{index + 1}"),
            step_type=StepType[step_type_str],
            agent_type=step_def.get("agent_type", ""),
            audit_type=AuditType[audit_type_str],
            depends_on=step_def.get("depends_on", []),
            params=step_def.get("params", {}),
            required=step_def.get("required", True),
            description=step_def.get("description", ""),
            max_retries=self.config.retry_config.max_retries,
        )

        return step

    def _execute_step(self, step: WorkflowStep, input_data: Any, workflow: Workflow) -> Any:
        """执行单个步骤

        Args:
            step: 工作流步骤
            input_data: 输入数据
            workflow: 工作流

        Returns:
            Any: 执行结果
        """
        self.monitor.log_step_start(step)

        # 获取Agent
        agent = self.agent_registry.get(step.agent_type)

        if not agent:
            raise AgentException(f"未找到Agent: {step.agent_type}")

        # 准备参数
        params = {**step.params}
        if "input_data" in params or input_data is not None:
            params["input_data"] = input_data

        # 重试执行
        retry_context = {"step": step, "workflow": workflow}

        def execute_with_retry():
            return agent.execute(**params)

        try:
            result = self.retry_manager.execute_with_retry(
                execute_with_retry,
                should_retry=self.retry_manager.should_retry_on_exception,
                on_retry=lambda e, attempt: self.monitor.log(
                    f"重试 {attempt}/{self.config.retry_config.max_retries}: {str(e)}"
                ),
            )

            return result

        except Exception as e:
            self.monitor.log(f"步骤执行失败: {str(e)}")
            raise

    def _generate_workflow_report(self, workflow: Workflow):
        """生成工作流报告

        Args:
            workflow: 工作流
        """
        if not self.config.workflow_config.generate_report:
            return

        # 生成报告
        workflow_instance = self.workflow_manager.workflows.get(workflow.workflow_id)
        if not workflow_instance:
            self.monitor.log(f"警告：无法找到工作流 {workflow.workflow_id}")
            return
        report = workflow_instance.get_summary()

        # 保存报告
        if self.config.workflow_config.report_path:
            report_path = self.config.workflow_config.report_path
        else:
            date_str = datetime.now().strftime("%Y%m%d")
            report_path = f"{self.config.workspace_path}/{date_str}/workflow_report_{workflow.workflow_id}.json"

        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self.monitor.log(f"报告已生成: {report_path}")

    def execute_test_case_generation(self, requirement_id: str, requirement_name: str, test_cases: list[dict]) -> str:
        """执行测试用例生成工作流

        Args:
            requirement_id: 需求ID
            requirement_name: 需求名称
            test_cases: 测试用例列表

        Returns:
            str: 生成的Excel文件路径
        """
        workflow_def = {
            "name": f"测试用例生成 - {requirement_name}",
            "description": f"为需求{requirement_id}生成测试用例",
            "steps": [
                {
                    "step_id": "step_prepare",
                    "name": "准备数据",
                    "type": "AGENT",
                    "agent_type": "test_case_generator",
                    "audit_type": "TEST_CASE",
                    "params": {"operation": "validate"},
                },
                {
                    "step_id": "step_generate",
                    "name": "生成测试用例",
                    "type": "AGENT",
                    "agent_type": "test_case_generator",
                    "audit_type": "TEST_CASE",
                    "depends_on": ["step_prepare"],
                    "params": {"operation": "create"},
                },
                {
                    "step_id": "step_export",
                    "name": "导出Excel",
                    "type": "EXPORT",
                    "agent_type": "excel_generator",
                    "audit_type": "ALL",
                    "depends_on": ["step_generate"],
                    "params": {"requirement_name": requirement_name, "requirement_id": requirement_id},
                },
            ],
        }

        # 执行工作流
        workflow = self.execute_workflow(workflow_def, test_cases)

        # 获取输出
        export_step = workflow.get_step("step_export")
        if export_step and export_step.result:
            return export_step.result

        return ""

    def execute_code_review(self, code: str, language: str = "python") -> AuditResult:
        """执行代码审核工作流

        Args:
            code: 代码内容
            language: 编程语言

        Returns:
            AuditResult: 审核结果
        """
        workflow_def = {
            "name": f"代码审核 - {language}",
            "description": f"审核{language}代码",
            "steps": [
                {
                    "step_id": "step_code_audit",
                    "name": "代码规范审核",
                    "type": "AUDIT",
                    "audit_type": "CODE",
                    "params": {"language": language},
                },
                {
                    "step_id": "step_security_audit",
                    "name": "安全审核",
                    "type": "AUDIT",
                    "audit_type": "SECURITY",
                    "depends_on": ["step_code_audit"],
                },
            ],
        }

        # 执行工作流
        workflow = self.execute_workflow(workflow_def, code)

        # 获取审核结果
        if workflow.status == WorkflowStatus.FAILED:
            failed = AuditResult()
            failed.passed = False
            failed.add_error("WORKFLOW_EXECUTION_FAILED", workflow.error_message or "代码审核工作流执行失败")
            return failed

        # 返回最后一个审核结果
        for step in reversed(workflow.steps):
            if step.audit_result:
                return step.audit_result

        return AuditResult()

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """获取工作流状态

        Args:
            workflow_id: 工作流ID

        Returns:
            Dict: 工作流状态
        """
        return self.workflow_manager.get_workflow_status(workflow_id)

    def list_active_workflows(self) -> list[dict[str, Any]]:
        """列出活跃的工作流

        Returns:
            list[dict]: 工作流列表
        """
        workflows = self.workflow_manager.list_workflows()
        return [wf for wf in workflows if wf.get("is_running")]

    def pause_workflow(self, workflow_id: str):
        """暂停工作流

        Args:
            workflow_id: 工作流ID
        """
        workflow = self.workflow_manager.get_workflow(workflow_id)
        if workflow:
            if workflow.state != "running":
                logger.warning("工作流 %s 当前状态为 %s，无法暂停", workflow_id, workflow.state)
                return False
            self.workflow_manager.transition(workflow_id, "pause")
            logger.info("工作流 %s 已暂停", workflow_id)
            self.monitor.log(f"工作流已暂停: {workflow_id}")
            return True
        logger.warning("工作流 %s 不存在，无法暂停", workflow_id)
        return False

    def resume_workflow(self, workflow_id: str):
        """恢复工作流

        Args:
            workflow_id: 工作流ID
        """
        workflow = self.workflow_manager.get_workflow(workflow_id)
        if workflow:
            if workflow.state != "paused":
                logger.warning("工作流 %s 当前状态为 %s，无法恢复", workflow_id, workflow.state)
                return False
            self.workflow_manager.transition(workflow_id, "resume")
            logger.info("工作流 %s 已恢复", workflow_id)
            self.monitor.log(f"工作流已恢复: {workflow_id}")
            return True
        logger.warning("工作流 %s 不存在，无法恢复", workflow_id)
        return False
