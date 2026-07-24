"""代码规范审核器"""

import ast
import os
from pathlib import Path
from typing import Any

from ..audit_models import AuditResult
from ..config import AuditType
from ..audit_rules import RuleManager


class CodeAuditor:
    """代码规范审核器"""

    def __init__(self, rule_manager: RuleManager | None = None):
        """初始化代码规范审核器

        Args:
            rule_manager: 可选的 RuleManager 实例
        """
        self.rule_manager = rule_manager or RuleManager()

    def audit(self, code: Any, language: str = "python") -> AuditResult:
        """审核代码规范

        修复：完整传递 language 参数，不再仅依赖 context.get("language")

        Args:
            code: 代码内容（字符串或文件路径）
            language: 编程语言，默认 "python"

        Returns:
            AuditResult: 审核结果
        """
        result = AuditResult()
        result.audit_type = AuditType.CODE

        # 如果是文件路径，读取内容
        if isinstance(code, (str, Path)) and os.path.isfile(str(code)):
            try:
                with open(code, encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                result.add_error("CODE_READ_ERROR", f"无法读取代码文件: {str(e)}")
                return result

        if not isinstance(code, str):
            result.add_error("CODE_NOT_STRING", "代码必须是字符串格式")
            return result

        if not code.strip():
            result.add_error("CODE_EMPTY", "代码内容为空")
            return result

        # 根据语言执行审核
        if language.lower() == "python":
            self._audit_python_code(code, result)
        else:
            self._audit_generic_code(code, result, language)

        return result

    def _audit_python_code(self, code: str, result: AuditResult):
        """审核Python代码

        Args:
            code: Python代码
            result: 审核结果对象
        """
        try:
            tree = ast.parse(code)

            # 检查代码风格问题
            lines = code.split("\n")

            for i, line in enumerate(lines, start=1):
                # 检查行长度
                if len(line) > 120:
                    result.add_warning(
                        "CODE_LINE_TOO_LONG",
                        f"第{i}行超过120字符，建议拆分为多行",
                        f"第{i}行",
                    )

                # 检查Tab vs 空格混用
                if "\t" in line and "    " in line:
                    result.add_warning(
                        "CODE_TAB_SPACE_MIX",
                        f"第{i}行混用Tab和空格",
                        f"第{i}行",
                    )

                # 检查行尾空格
                if line.rstrip() != line:
                    result.add_warning(
                        "CODE_TRAILING_SPACE",
                        f"第{i}行包含尾随空格",
                        f"第{i}行",
                    )

            # 检查导入
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    pass  # 基础导入，无问题
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("_"):
                        result.add_warning(
                            "CODE_PRIVATE_IMPORT",
                            f"导入了私有模块: {node.module}",
                        )

        except SyntaxError as e:
            result.add_error("CODE_SYNTAX_ERROR", f"语法错误: {str(e)}", f"第{e.lineno}行")
        except (ValueError, TypeError) as e:
            result.add_error("CODE_PARSE_ERROR", f"代码解析错误: {str(e)}")

    def _audit_generic_code(self, code: str, result: AuditResult, language: str = ""):
        """通用代码审核

        Args:
            code: 代码
            result: 审核结果对象
            language: 编程语言名称
        """
        lines = code.split("\n")

        for i, line in enumerate(lines, start=1):
            # 检查行长度
            if len(line) > 120:
                result.add_warning(
                    "CODE_LINE_TOO_LONG",
                    f"第{i}行超过120字符",
                    f"第{i}行",
                )

            # 检查可疑注释
            if "TODO" in line or "FIXME" in line:
                result.add_warning(
                    "CODE_TODO_COMMENT",
                    f"第{i}行包含TODO/FIXME注释",
                    f"第{i}行",
                )

    # --- 以下方法为扩展预留 ---

    def _check_code_readability(self, code: str, result: AuditResult):
        """检查代码可读性"""
        self._audit_generic_code(code, result)

    def _check_code_structure(self, code: str, result: AuditResult):
        """检查代码结构"""
        if self._is_python_code(code):
            self._audit_python_code(code, result)

    def _check_imports(self, code: str, result: AuditResult):
        """检查导入语句"""
        if self._is_python_code(code):
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith("_"):
                            result.add_warning(
                                "CODE_PRIVATE_IMPORT",
                                f"导入了私有模块: {node.module}",
                            )
            except SyntaxError:
                pass

    def _check_naming_conventions(self, code: str, result: AuditResult):
        """检查命名规范"""
        # 预留：可使用 pylint 等工具集成
        pass

    def _check_docstrings(self, code: str, result: AuditResult):
        """检查文档字符串"""
        # 预留：可检查函数/类是否有 docstring
        pass

    def _check_error_handling(self, code: str, result: AuditResult):
        """检查错误处理"""
        # 预留：可检查 try/except 覆盖情况
        pass

    @staticmethod
    def _is_python_code(code: str) -> bool:
        """判断是否为Python代码"""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False
