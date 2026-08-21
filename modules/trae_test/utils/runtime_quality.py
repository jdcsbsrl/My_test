"""测试用例运行时质量契约。

评分轨迹、冷启动元数据和覆盖矩阵属于运行时/审核报告数据，不能扩展正式15列
Excel模板。该模块提供稳定的字段名和序列化边界，供生成、审核和报告链路复用。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

RUNTIME_QUALITY_VERSION = "1.0"
QUALITY_SCORE_THRESHOLD = 85.0

RUNTIME_QUALITY_KEY = "_runtime_quality"
RUNTIME_QUALITY_VERSION_KEY = "_runtime_quality_version"
RUNTIME_QUALITY_FIELDS = (
    "original_score",
    "optimized_score",
    "final_score",
    "score_history",
    "score_threshold",
    "is_cold_start",
    "confidence",
    "optimization_attempts",
    "needs_human_review",
    "final_audit_passed",
)


@dataclass(slots=True)
class RuntimeQualitySnapshot:
    """单条用例的运行时评分状态，不对应任何Excel列。"""

    original_score: float | None = None
    optimized_score: float | None = None
    final_score: float | None = None
    score_history: list[dict[str, Any]] = field(default_factory=list)
    score_threshold: float = QUALITY_SCORE_THRESHOLD
    is_cold_start: bool = False
    confidence: float = 0.0
    optimization_attempts: int = 0
    needs_human_review: bool = False
    final_audit_passed: bool = False

    def __post_init__(self) -> None:
        for name in ("original_score", "optimized_score", "final_score"):
            value = getattr(self, name)
            if value is not None and not 0 <= float(value) <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if int(self.optimization_attempts) < 0:
            raise ValueError("optimization_attempts must be non-negative")
        self.score_history = [dict(item) for item in self.score_history if isinstance(item, Mapping)]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "RuntimeQualitySnapshot":
        value = value or {}
        return cls(**{name: value.get(name) for name in RUNTIME_QUALITY_FIELDS if name in value})


def attach_runtime_quality(
    case: dict[str, Any], snapshot: RuntimeQualitySnapshot | Mapping[str, Any]
) -> dict[str, Any]:
    """把评分状态写入运行时命名空间，保持正式15列字段不变。"""

    normalized = snapshot if isinstance(snapshot, RuntimeQualitySnapshot) else RuntimeQualitySnapshot.from_mapping(snapshot)
    case[RUNTIME_QUALITY_KEY] = normalized.to_dict()
    case[RUNTIME_QUALITY_VERSION_KEY] = RUNTIME_QUALITY_VERSION
    return case


def read_runtime_quality(case: Mapping[str, Any]) -> RuntimeQualitySnapshot:
    """读取嵌套运行时质量状态；缺失时返回默认快照。"""

    value = case.get(RUNTIME_QUALITY_KEY)
    if isinstance(value, Mapping):
        return RuntimeQualitySnapshot.from_mapping(value)
    return RuntimeQualitySnapshot()

