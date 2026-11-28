"""Markdown 需求测试计划审核器。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..audit_models import AuditResult
from ..config import AuditType


class TestPlanAuditor:
    """检查测试计划的归档路径、命名和最低结构契约。

    此审核不证明业务语义正确，也不替代正式测试用例的 15 字段审核。
    """

    REQUIRED_SECTIONS = (
        "## 摘要",
        "## 需求与场景矩阵",
        "## 七维覆盖自查",
        "## 覆盖自查",
        "## 排除项和未决问题",
        "## 回归范围",
    )
    REQUIRED_MATRIX_FIELDS = (
        "场景 ID",
        "需求 ID",
        "证据 ID",
        "覆盖维度",
        "优先级",
        "账号/权限",
        "页面入口",
        "数据/状态",
        "页面对象",
        "可观察预期",
        "测试方式",
        "覆盖状态",
        "依据状态",
    )
    BASE_COVERAGE_DIMENSIONS = (
        "业务规则",
        "业务对象",
        "正常场景",
        "异常场景",
        "边界场景",
        "回滚场景",
        "排除项",
    )
    PLAN_NAME_PATTERN = re.compile(r"需求.+_测试计划(?:_修订\d{2})?\.md")
    FORBIDDEN_FILENAME_CHARS = set('\\/:*?"<>|')
    MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+)$")
    MARKDOWN_TABLE_SEPARATOR_PATTERN = re.compile(r":?-{3,}:?")
    MARKDOWN_FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")

    def audit(self, target: Any, context: dict | None = None) -> AuditResult:
        """审核 Markdown 内容或已保存的计划路径。"""
        result = AuditResult()
        result.audit_type = AuditType.TEST_PLAN
        context = context or {}
        plan_path, content = self._read_target(target, result)
        if content is None:
            return result

        if not content.strip():
            result.add_error("TEST_PLAN_EMPTY", "测试计划内容为空", str(plan_path or ""))
            return result

        if plan_path is not None:
            self._check_path(plan_path, result, context)

        headings = self._markdown_headings(content)
        for section in self.REQUIRED_SECTIONS:
            title = section.removeprefix("## ")
            if (2, title) not in {(level, heading) for _, level, heading in headings}:
                result.add_error("TEST_PLAN_SECTION_MISSING", f"测试计划缺少章节：{section}", str(plan_path or ""))

        matrix_content = self._section_content(content, headings, "需求与场景矩阵")
        matrix_tables = self._markdown_tables(matrix_content)
        matrix_headers = matrix_tables[0][0] if matrix_tables else []
        for field in self.REQUIRED_MATRIX_FIELDS:
            if not any(field.casefold() in header.casefold() for header in matrix_headers):
                result.add_error(
                    "TEST_PLAN_MATRIX_FIELD_MISSING", f"测试计划矩阵缺少字段：{field}", str(plan_path or "")
                )

        coverage_content = self._section_content(content, headings, "七维覆盖自查")
        coverage_tables = self._markdown_tables(coverage_content)
        coverage_rows = {row[0] for _, rows in coverage_tables for row in rows if row}
        for dimension in self.BASE_COVERAGE_DIMENSIONS:
            if dimension not in coverage_rows:
                result.add_error(
                    "TEST_PLAN_COVERAGE_DIMENSION_MISSING", f"未检查基础覆盖维度：{dimension}", str(plan_path or "")
                )

        result.add_suggestion("结构审核通过不代表业务语义已被证明；待确认项仍须由用户审阅。")
        return result

    @classmethod
    def _markdown_headings(cls, content: str) -> list[tuple[int, int, str]]:
        headings = []
        for line_number, line in enumerate(cls._visible_markdown_lines(content)):
            match = cls.MARKDOWN_HEADING_PATTERN.match(line.strip())
            if not match:
                continue
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
            headings.append((line_number, len(match.group(1)), title))
        return headings

    @classmethod
    def _section_content(cls, content: str, headings: list[tuple[int, int, str]], title: str) -> str:
        lines = cls._visible_markdown_lines(content)
        start = next(
            (line_number for line_number, level, heading in headings if level == 2 and heading == title),
            None,
        )
        if start is None:
            return ""

        end = next(
            (line_number for line_number, level, _ in headings if line_number > start and level <= 2),
            len(lines),
        )
        return "\n".join(lines[start + 1 : end])

    @classmethod
    def _markdown_tables(cls, content: str) -> list[tuple[list[str], list[list[str]]]]:
        lines = cls._visible_markdown_lines(content)
        tables = []
        index = 0
        while index + 1 < len(lines):
            header_line = lines[index].strip()
            separator_line = lines[index + 1].strip()
            if not header_line.startswith("|") or not separator_line.startswith("|"):
                index += 1
                continue

            headers = [cell.strip() for cell in header_line.strip("|").split("|")]
            separators = [cell.strip() for cell in separator_line.strip("|").split("|")]
            if len(headers) != len(separators) or not all(
                cls.MARKDOWN_TABLE_SEPARATOR_PATTERN.fullmatch(cell) for cell in separators
            ):
                index += 1
                continue

            rows = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                rows.append(row)
                index += 1
            tables.append((headers, rows))
        return tables

    @classmethod
    def _visible_markdown_lines(cls, content: str) -> list[str]:
        """Return Markdown lines outside fenced code blocks."""
        visible_lines = []
        fence_character = None
        fence_length = 0

        for line in content.splitlines():
            stripped = line.lstrip()
            if fence_character is None:
                match = cls.MARKDOWN_FENCE_PATTERN.match(stripped)
                if match:
                    fence = match.group(1)
                    fence_character = fence[0]
                    fence_length = len(fence)
                    visible_lines.append("")
                    continue
                visible_lines.append(line)
                continue

            closing_fence = re.fullmatch(rf"{re.escape(fence_character)}{{{fence_length},}}[ \t]*", stripped)
            if closing_fence:
                fence_character = None
                fence_length = 0
            visible_lines.append("")

        return visible_lines

    def _read_target(self, target: Any, result: AuditResult) -> tuple[Path | None, str | None]:
        if isinstance(target, Path):
            path = target
        elif isinstance(target, str) and "\n" not in target and Path(target).suffix.lower() == ".md":
            path = Path(target)
        elif isinstance(target, str):
            return None, target
        else:
            result.add_error("TEST_PLAN_INPUT_INVALID", "审核目标必须是 Markdown 文本或 .md 文件路径")
            return None, None

        if not path.is_file():
            result.add_error("TEST_PLAN_FILE_MISSING", "测试计划文件不存在", str(path))
            return path, None
        try:
            return path, path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            result.add_error("TEST_PLAN_READ_FAILED", f"无法读取测试计划：{exc}", str(path))
            return path, None

    def _check_path(self, path: Path, result: AuditResult, context: dict) -> None:
        normalized = path.as_posix()
        match = re.search(r"(?:^|/)workspace/(\d{8})/([^/]+)$", normalized, re.IGNORECASE)
        if not match:
            result.add_error("TEST_PLAN_PATH_INVALID", "测试计划必须放在 workspace/YYYYMMDD/ 下", normalized)
        else:
            try:
                datetime.strptime(match.group(1), "%Y%m%d")
            except ValueError:
                result.add_error("TEST_PLAN_DATE_INVALID", "测试计划目录日期必须为有效 YYYYMMDD", normalized)

        filename = path.name
        if not self.PLAN_NAME_PATTERN.fullmatch(filename):
            result.add_error(
                "TEST_PLAN_NAME_INVALID", "测试计划文件名应为 需求{ID}{名称}_测试计划.md，可附 _修订NN", filename
            )
        if any(char in filename for char in self.FORBIDDEN_FILENAME_CHARS):
            result.add_error("TEST_PLAN_NAME_INVALID", "测试计划文件名包含 Windows 禁用字符", filename)

        project_root = Path(context.get("project_root", Path(__file__).resolve().parents[4]))
        workspace_root = (project_root / "workspace").resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(workspace_root)
        except ValueError:
            result.add_error(
                "TEST_PLAN_PATH_OUTSIDE_PROJECT", "测试计划路径必须位于当前项目的 workspace 下", normalized
            )
