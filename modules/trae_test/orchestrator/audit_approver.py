"""操作前审批管理器 - 从审核中分离的审批逻辑"""

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .config import AuditConfig


# 延迟导入，避免循环依赖
# OperationType 在 audit_agent_enhanced.py 中定义
# 通过 _get_operation_type() 函数延迟获取


def _get_operation_type():
    """延迟获取 OperationType 枚举，避免循环依赖"""
    from .audit_agent_enhanced import OperationType

    return OperationType


class AuditApprover:
    """操作前审批管理器 - 从审核中分离的审批逻辑"""

    def __init__(self, config: AuditConfig, notify_callback: Callable | None = None):
        """初始化审批管理器

        Args:
            config: 审核配置
            notify_callback: 通知回调函数
        """
        self.config = config
        self.notify_callback = notify_callback or print
        self.user_approved = False
        self._is_ci = os.getenv("CI", "").lower() in ("true", "1", "yes")
        if self._is_ci:
            print("[AuditApprover] 检测到 CI 环境，交互审批模式已禁用")

        # 需要审批的操作类型（延迟初始化）
        self._requires_approval = None

    @property
    def _approval_set(self):
        """延迟加载需要审批的操作类型集合"""
        if self._requires_approval is None:
            OperationType = _get_operation_type()
            self._requires_approval = {
                OperationType.CODE_GENERATION,
                OperationType.FOLDER_CREATION,
                OperationType.FILE_DELETE,
                OperationType.CONFIG_CHANGE,
            }
        return self._requires_approval

    def needs_approval(self, context: dict) -> bool:
        """判断操作是否需要审批

        Args:
            context: 操作上下文

        Returns:
            bool: 是否需要审批
        """
        OperationType = _get_operation_type()
        operation_type = OperationType.from_context(context)
        return operation_type in self._approval_set

    def request_approval(self, context: dict) -> dict[str, Any]:
        """请求用户审批操作

        Args:
            context: 操作上下文

        Returns:
            Dict: 审批结果 {'approved': bool, 'reason': str}
        """
        OperationType = _get_operation_type()
        operation_type = OperationType.from_context(context)
        action = context.get("action", "执行操作")
        target = context.get("target", "未知目标")
        purpose = context.get("purpose", "未说明目的")

        # 构建审批请求信息
        approval_message = self._build_approval_message(operation_type, action, target, purpose)

        # 显示审批信息
        print("\n" + "=" * 80)
        print("[操作审批请求]")
        print("=" * 80)
        print(approval_message)
        print("=" * 80)

        # 根据环境决定审批策略
        self.user_approved = self._prompt_user_approval()

        return {"approved": self.user_approved, "reason": "用户已批准" if self.user_approved else "用户拒绝/审核阻断"}

    def prompt_before_operation(self, action: str, target: str, purpose: str = "") -> bool:
        """操作前审核 - 明确告知用户操作目的并请求批准

        Args:
            action: 操作动作
            target: 操作目标
            purpose: 操作目的

        Returns:
            bool: 是否获得批准
        """
        context = {"action": action, "target": target, "purpose": purpose}

        print("\n" + "=" * 80)
        print("[操作前审核]")
        print("=" * 80)
        print("操作动作: %s" % action)
        print("操作目标: %s" % target)
        print("操作目的: %s" % (purpose if purpose else "未说明"))
        print("=" * 80)

        if self.needs_approval(context):
            OperationType = _get_operation_type()
            print("\n[WARN] 此操作需要您的批准！")
            print("\n[操作详情]:")
            print("  - 类型: %s" % OperationType.from_context(context).value)
            print("  - 动作: %s" % action)
            print("  - 目标: %s" % target)
            print("  - 目的: %s" % purpose)

            self.user_approved = self._prompt_user_approval()

            return self.user_approved
        else:
            print("[OK] 此操作无需审批，可直接执行")
            return True

    def _prompt_user_approval(self) -> bool:
        """统一的用户审批交互逻辑

        Returns:
            bool: 用户是否批准
        """
        if self.config.interactive_mode and not self._is_ci:
            try:
                user_input = input("\n请确认是否允许执行此操作？(y/n): ").strip().lower()
                return user_input in ("y", "yes", "是", "")
            except (EOFError, KeyboardInterrupt):
                print("\n[WARN] 无法获取用户输入，操作已被拒绝")
                return False
        elif self.config.auto_approve:
            print("\n[WARN] 操作已自动批准（auto_approve=True），请确保此设置在安全环境中使用")
            return True
        else:
            print("\n[BLOCK] 审核阻断：操作需要用户批准但当前为非交互环境")
            print("[HINT] 设置 AuditConfig(interactive_mode=True) 启用交互审批")
            print("[HINT] 或在可信环境中设置 AuditConfig(auto_approve=True) 自动批准")
            return False

    def _build_approval_message(self, operation_type: Any, action: str, target: str, purpose: str) -> str:
        """构建审批请求消息

        Args:
            operation_type: 操作类型
            action: 操作动作
            target: 操作目标
            purpose: 操作目的

        Returns:
            str: 审批消息
        """
        OperationType = _get_operation_type()

        type_descriptions = {
            OperationType.CODE_GENERATION: "代码生成",
            OperationType.FOLDER_CREATION: "文件夹创建",
            OperationType.FILE_DELETE: "文件删除",
            OperationType.CONFIG_CHANGE: "配置变更",
        }

        lines = [
            f"操作类型: {type_descriptions.get(operation_type, operation_type.value)}",
            f"操作动作: {action}",
            f"操作目标: {target}",
            f"操作目的: {purpose}",
            "",
            "请确认是否允许执行此操作？",
            "",
            "[注意] 此操作可能会影响项目结构或代码，请仔细确认！",
        ]

        return "\n".join(lines)
