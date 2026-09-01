"""需求级测试覆盖矩阵模型与运行时字段工具。

覆盖矩阵只存在于运行时对象和审核报告中，不参与正式 15 列 Excel 导出。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(slots=True)
class CoverageMatrix:
    """描述一个需求需要覆盖的业务维度。"""

    business_rules: list[str] = field(default_factory=list)
    business_objects: list[str] = field(default_factory=list)
    normal_scenarios: list[str] = field(default_factory=list)
    abnormal_scenarios: list[str] = field(default_factory=list)
    boundary_scenarios: list[str] = field(default_factory=list)
    rollback_scenarios: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in self.field_names():
            values = getattr(self, name)
            setattr(self, name, _unique_strings(values))

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(cls.__dataclass_fields__)  # type: ignore[attr-defined]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "CoverageMatrix":
        """从运行时字典构造矩阵，忽略未知字段以保持向后兼容。"""
        value = value or {}
        return cls(**{name: value.get(name, []) for name in cls.field_names()})

    def to_dict(self) -> dict[str, list[str]]:
        return asdict(self)

    def merge(self, other: "CoverageMatrix") -> "CoverageMatrix":
        """合并需求级矩阵，保持字段顺序和条目顺序稳定。"""
        return CoverageMatrix(**{name: [*getattr(self, name), *getattr(other, name)] for name in self.field_names()})

    def missing_from(self, covered: Mapping[str, Iterable[str]]) -> dict[str, list[str]]:
        """返回各维度尚未被用例覆盖的条目。"""
        missing: dict[str, list[str]] = {}
        for name in self.field_names():
            required = set(getattr(self, name))
            actual = set(_unique_strings(covered.get(name, [])))
            if required - actual:
                missing[name] = sorted(required - actual)
        return missing


def attach_coverage_matrix(case: dict[str, Any], matrix: CoverageMatrix | Mapping[str, Any]) -> dict[str, Any]:
    """把覆盖矩阵写入用例运行时字段，原地更新并返回用例。

    字段使用 ``_runtime_`` 前缀，Excel 生成器不应读取这些字段。
    """
    normalized = matrix if isinstance(matrix, CoverageMatrix) else CoverageMatrix.from_mapping(matrix)
    case["_runtime_coverage_matrix"] = normalized.to_dict()
    case["_runtime_coverage_matrix_version"] = "1.0"
    return case


def read_coverage_matrix(case: Mapping[str, Any]) -> CoverageMatrix:
    """读取用例中的覆盖矩阵；缺失时返回空矩阵。"""
    return CoverageMatrix.from_mapping(case.get("_runtime_coverage_matrix"))


def build_requirement_coverage_matrix(
    requirement: str,
    knowledge: Any = None,
    scenario_type: str | None = None,
) -> CoverageMatrix:
    """从需求文本和知识检索结果构建最小需求级覆盖矩阵。

    这里只登记文本中明确出现或由生成器已确定的覆盖项，不凭空扩展业务范围。
    结果用于运行时审核/报告，不进入正式15列Excel。
    """
    knowledge_items: list[str] = []
    if isinstance(knowledge, Mapping):
        knowledge_items = [str(key).strip() for key in knowledge if str(key).strip()]
        knowledge_text = " ".join(str(value) for value in knowledge.values())
    elif isinstance(knowledge, list):
        knowledge_text = " ".join(str(item) for item in knowledge)
    else:
        knowledge_text = str(knowledge or "")

    text = f"{requirement} {knowledge_text}".strip()
    normal = _terms(text, ("正常", "成功", "主流程", "正常流程"))
    abnormal = _terms(text, ("异常", "失败", "错误", "无效", "拒绝", "拦截"))
    boundary = _terms(text, ("边界", "最大", "最小", "上限", "下限", "为空", "超出"))
    rollback = _terms(text, ("回滚", "撤销", "冲正", "恢复"))
    exclusions = _extract_exclusions(text)

    if scenario_type == "normal" and not normal:
        normal = [requirement.strip()]
    elif scenario_type in {"exception", "abnormal"} and not abnormal:
        abnormal = [requirement.strip()]
    elif scenario_type == "boundary" and not boundary:
        boundary = [requirement.strip()]

    objects = _terms(
        text,
        ("订单", "商品", "SKU", "客户", "库存", "仓库", "价格", "金额", "用户", "权限", "状态"),
    )
    return CoverageMatrix(
        business_rules=knowledge_items or _terms(text, ("必须", "不得", "仅", "允许", "禁止")),
        business_objects=objects,
        normal_scenarios=normal,
        abnormal_scenarios=abnormal,
        boundary_scenarios=boundary,
        rollback_scenarios=rollback,
        exclusions=exclusions,
    )


def _terms(text: str, keywords: Iterable[str]) -> list[str]:
    """返回按关键词首次出现顺序归一化的覆盖条目。"""
    lowered = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lowered]


def _extract_exclusions(text: str) -> list[str]:
    """提取明确的排除范围，避免把未声明内容当作覆盖要求。"""
    markers = ("不包含", "不涉及", "不考虑", "排除")
    result: list[str] = []
    for marker in markers:
        start = text.find(marker)
        if start < 0:
            continue
        tail = text[start + len(marker) :].strip(" ：:，,。;；")
        if tail:
            result.append(tail.split("。", 1)[0].split("，", 1)[0].split(",", 1)[0].strip())
    return _unique_strings(result)


def _unique_strings(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result
