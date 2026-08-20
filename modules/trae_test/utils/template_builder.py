"""测试用例Excel模板构建器

历史上模板文件`fixtures/templates/测试用例模板.xlsx`被当作手工维护的二进制资产，
新机器 clone 后常常缺失，导致 test_case_generator / test_artifact_generator 直接抛错。

本模块严格对齐知识库《测试用例模板与优先级规则》（assets/knowledge_base/测试规范/测试用例模板与优先级规则.json）规定的 15 字段（11 导入 + 4 扩展），
铁律："模板没有的字段绝对不能出现"、"禁止额外字段"、"质量评分必须在第15列"。

所有 generator 在写入数据前都应先调用 `ensure_template()`，确保模板链路永远可用。
"""

from __future__ import annotations

import os
from pathlib import Path

IMPORT_FIELDS: list[str] = [
    "用例目录",
    "用例名称",
    "需求ID",
    "前置条件",
    "用例步骤",
    "预期结果",
    "用例类型",
    "用例状态",
    "用例等级",
    "创建人",
    "优先级",
]
EXTENSION_FIELDS: list[str] = [
    "是否可自动化",
    "回归测试标识",
    "知识库关联",
    "质量评分",
]
ALL_FIELDS: list[str] = IMPORT_FIELDS + EXTENSION_FIELDS

COLUMN_WIDTHS = {
    "用例目录": 25,
    "用例名称": 40,
    "需求ID": 12,
    "前置条件": 30,
    "用例步骤": 40,
    "预期结果": 35,
    "用例类型": 12,
    "用例状态": 10,
    "用例等级": 10,
    "创建人": 12,
    "优先级": 8,
    "是否可自动化": 12,
    "回归测试标识": 15,
    "知识库关联": 15,
    "质量评分": 12,
}


def get_default_template_path() -> str:
    """返回项目内约定的模板路径（fixtures/templates/测试用例模板.xlsx）"""
    project_root = Path(__file__).resolve().parents[3]
    return str(project_root / "fixtures" / "templates" / "测试用例模板.xlsx")


def _template_header_matches(template_path: str) -> bool:
    """校验磁盘上的模板表头是否与当前 ALL_FIELDS 完全一致

    历史上曾错误扩展为 16/18 字段（包含关联缺陷ID或其他评估字段），
    当前契约固定为15字段。若磁盘模板与当前 ALL_FIELDS 不一致
    则拒绝继续，保证交付物永远符合规范且不覆盖现有资产。
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        return True  # 无法校验则保守不重建，避免 CI 无依赖时炸开

    wb = None
    try:
        wb = load_workbook(template_path, read_only=True)
        ws = wb["测试用例"]
        width = max(ws.max_column, len(ALL_FIELDS))
        header = [ws.cell(row=1, column=c).value for c in range(1, width + 1)]
        while header and header[-1] in (None, ""):
            header.pop()
        return header == ALL_FIELDS
    except Exception:
        return False
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


def ensure_template(template_path: str | None = None) -> str:
    """确保模板文件存在且表头字段与最新 ALL_FIELDS 对齐

    - 模板不存在：按知识库规定的 15 字段生成
    - 模板存在但表头不匹配（含历史错误的 16/18 字段）：拒绝继续，避免静默覆盖资产
    - 模板存在且字段一致：直接返回

    Args:
        template_path: 目标路径。None 则使用默认路径。

    Returns:
        最终可用的模板绝对路径。

    Raises:
        ImportError: openpyxl 未安装。
    """
    if template_path is None:
        template_path = get_default_template_path()

    if Path(template_path).exists():
        if _template_header_matches(template_path):
            return template_path
        raise ValueError(
            f"模板表头不符合15字段契约，拒绝覆盖现有文件: {template_path}"
        )

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise ImportError("请先安装 openpyxl：uv add openpyxl") from exc

    target = Path(template_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "测试用例"

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, field in enumerate(ALL_FIELDS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=field)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        width = COLUMN_WIDTHS.get(field, 15)
        ws.column_dimensions[cell.column_letter].width = width

    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    wb.save(target)
    return str(target)
