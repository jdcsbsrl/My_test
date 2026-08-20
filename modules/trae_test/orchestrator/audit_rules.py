"""审核规则管理器 - 管理审核规则的生命周期

职责：
- 从 YAML 配置加载规则（优先）
- 代码默认规则作为兜底
- TTL 缓存 + 文件修改自动失效
- 集成 TestCaseScoreEngine 质量评分
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认 YAML 配置文件路径（相对于项目根目录）
_DEFAULT_CONFIG_REL_PATH = "configs/audit_rules.yaml"

# 评分契约：审核/生成链路统一引用，低于此值不得作为最终交付。
FINAL_SCORE_THRESHOLD = 85.0
COLD_START_EXECUTION_THRESHOLD = 10


def is_final_score_qualified(score: float | None, *, is_cold_start: bool = False) -> bool:
    """返回最终评分门禁结果。

    冷启动只表示评分置信度较低，不能单独绕过业务审核；业务审核通过后，
    显式记录的最终评分仍可参与最终门禁。
    """
    return score is not None and score >= FINAL_SCORE_THRESHOLD


class RuleManager:
    """审核规则管理器 - 管理规则生命周期

    规则加载优先级：YAML 配置文件 > 代码默认规则
    缓存策略：TTL 缓存，到达过期时间后自动重新加载
    """

    def __init__(self, config_path: str | None = None, cache_ttl: int = 300):
        """初始化规则管理器

        Args:
            config_path: YAML 配置文件路径。为 None 时使用默认路径 configs/audit_rules.yaml
            cache_ttl: 缓存有效期（秒），默认 300 秒（5 分钟）
        """
        self._config_path = config_path or self._resolve_default_config_path()
        self._cache_ttl = cache_ttl

        # 缓存数据
        self._cache: dict[str, Any] = {}
        self._cache_timestamps: dict[str, float] = {}

        # TestCaseScoreEngine 实例（延迟导入，避免循环依赖）
        self._score_engine = None

    # ============================================================
    # 默认规则（代码级兜底）
    # ============================================================

    @staticmethod
    def default_field_value_rules() -> dict[str, Any]:
        """获取默认字段值校验规则（代码级兜底）

        当 YAML 配置文件不存在或加载失败时使用此默认值。
        """
        return {
        "用例状态": {
            "valid_values": ["正常"],
            "default_value": "正常",
            "required": True,
            "error_message": "用例状态只能为'正常'，审核和评分状态不得写入该字段",
        },
            "用例等级": {
                "valid_values": ["高", "中", "低"],
                "default_value": "中",
                "required": True,
                "error_message": "用例等级必须为'高'、'中'或'低'",
            },
            "优先级": {
                "valid_values": ["P0", "P1", "P2"],
                "default_value": "P1",
                "required": True,
                "error_message": "优先级必须为'P0'、'P1'或'P2'",
            },
            "用例类型": {
                "valid_values": ["功能测试", "接口测试", "性能测试", "安全测试", "兼容性测试"],
                "default_value": "功能测试",
                "required": True,
                "error_message": "用例类型必须为'功能测试'、'接口测试'、'性能测试'、'安全测试'或'兼容性测试'",
            },
            "是否可自动化": {
                "valid_values": ["是", "否"],
                "default_value": "否",
                "required": True,
                "error_message": "是否可自动化必须为'是'或'否'",
            },
            "回归测试标识": {
                "valid_values": ["是", "否"],
                "default_value": "否",
                "required": False,
                "error_message": "回归测试标识必须为'是'或'否'",
            },
            "创建人": {
                "valid_values": ["余小龙", "闫海燕"],
                "default_value": "余小龙",
                "required": True,
                "error_message": "创建人必须为有效测试人员姓名，当前仅允许：余小龙、闫海燕",
            },
        }

    @staticmethod
    def default_sensitive_patterns() -> list[tuple[str, str]]:
        """获取默认敏感信息模式（代码级兜底）

        返回 (正则表达式, 类型名称) 元组列表。
        """
        return [
            (r'password\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "password"),
            (r'passwd\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "passwd"),
            (r'pwd\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "pwd"),
            (r'api[_-]?key\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "api_key"),
            (r'secret\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{3,}["\']', "secret"),
            (r'token\s*=\s*["\'](?!xxx|\*\*\*|null)[^"\']{10,}["\']', "token"),
            (r"Bearer\s+[A-Za-z0-9\-_]{20,}", "bearer_token"),
        ]

    # ============================================================
    # 配置加载
    # ============================================================

    @staticmethod
    def _resolve_default_config_path() -> str:
        """解析默认配置文件路径（相对于项目根目录）"""
        return str(Path(__file__).resolve().parent.parent.parent.parent / _DEFAULT_CONFIG_REL_PATH)

    @staticmethod
    def _load_yaml_config(config_path: str) -> dict[str, Any] | None:
        """从 YAML 文件加载配置

        Args:
            config_path: YAML 文件路径

        Returns:
            解析后的配置字典，加载失败时返回 None
        """
        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML 未安装，无法加载 YAML 配置，将使用代码默认规则")
            return None

        if not os.path.isfile(config_path):
            logger.info("YAML 配置文件不存在: %s，将使用代码默认规则", config_path)
            return None

        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                logger.warning("YAML 配置文件格式无效: %s，将使用代码默认规则", config_path)
                return None
            logger.info("成功加载审核规则配置文件: %s", config_path)
            return data
        except Exception as e:
            logger.warning("加载 YAML 配置文件失败: %s (%s)，将使用代码默认规则", config_path, e)
            return None

    def _load_rules(self) -> dict[str, Any]:
        """加载规则（优先 YAML，兜底代码默认值）

        Returns:
            包含 field_value_rules 和 sensitive_patterns 的字典
        """
        yaml_data = self._load_yaml_config(self._config_path)

        if yaml_data:
            # 从 YAML 加载字段值规则
            field_rules = yaml_data.get("field_value_rules")
            if not isinstance(field_rules, dict):
                field_rules = self.default_field_value_rules()
                logger.info("YAML 中未找到 field_value_rules，使用默认规则")

            # 从 YAML 加载敏感信息模式
            raw_patterns = yaml_data.get("sensitive_patterns")
            if isinstance(raw_patterns, list):
                sensitive_patterns = []
                for item in raw_patterns:
                    if isinstance(item, dict) and "pattern" in item and "type" in item:
                        sensitive_patterns.append((item["pattern"], item["type"]))
                if not sensitive_patterns:
                    sensitive_patterns = self.default_sensitive_patterns()
                    logger.info("YAML 中 sensitive_patterns 为空，使用默认规则")
            else:
                sensitive_patterns = self.default_sensitive_patterns()
                logger.info("YAML 中未找到 sensitive_patterns，使用默认规则")
        else:
            field_rules = self.default_field_value_rules()
            sensitive_patterns = self.default_sensitive_patterns()

        return {
            "field_value_rules": field_rules,
            "sensitive_patterns": sensitive_patterns,
        }

    # ============================================================
    # 缓存管理
    # ============================================================

    def _cleanup_expired_cache(self):
        """清理过期的缓存键"""
        now = time.time()
        expired_keys = [
            key for key, timestamp in self._cache_timestamps.items()
            if now - timestamp >= self._cache_ttl
        ]
        for key in expired_keys:
            del self._cache[key]
            del self._cache_timestamps[key]

    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        self._cleanup_expired_cache()
        if key not in self._cache or key not in self._cache_timestamps:
            return False
        elapsed = time.time() - self._cache_timestamps[key]
        return elapsed < self._cache_ttl

    def _get_cached_or_load(self, key: str) -> Any:
        """从缓存获取数据，缓存失效时重新加载"""
        if not self._is_cache_valid(key):
            rules_data = self._load_rules()
            for k, v in rules_data.items():
                self._cache[k] = v
                self._cache_timestamps[k] = time.time()
        return self._cache.get(key)

    def refresh(self) -> None:
        """强制刷新所有缓存规则

        下次调用 get_field_value_rules() 或 get_sensitive_patterns() 时会重新加载配置。
        """
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("审核规则缓存已强制刷新")

    def clear_cache(self) -> None:
        """清空所有缓存（同 refresh，提供更语义化的别名）"""
        self.refresh()

    # ============================================================
    # 字段值规则
    # ============================================================

    def get_field_value_rules(self) -> dict[str, Any]:
        """获取字段值校验规则"""
        return dict(self._get_cached_or_load("field_value_rules"))

    def get_field_valid_values(self, field_name: str) -> list[str]:
        """获取指定字段的合法值列表

        Args:
            field_name: 字段名称（如 "用例状态"、"优先级"）

        Returns:
            合法值列表，字段不存在时返回空列表
        """
        rules = self.get_field_value_rules()
        field_rule = rules.get(field_name)
        if field_rule and isinstance(field_rule, dict):
            return list(field_rule.get("valid_values", []))
        return []

    def validate_field_value(self, field_name: str, value: str) -> tuple[bool, str]:
        """校验字段值是否合法

        Args:
            field_name: 字段名称
            value: 待校验的字段值

        Returns:
            (是否合法, 错误消息)
            合法时错误消息为空字符串，非法时返回配置的 error_message 或默认提示
        """
        rules = self.get_field_value_rules()
        field_rule = rules.get(field_name)

        if not field_rule:
            # 未配置规则的字段默认通过
            return True, ""

        valid_values = field_rule.get("valid_values", [])
        if value in valid_values:
            return True, ""

        error_message = field_rule.get("error_message", f"字段 '{field_name}' 的值 '{value}' 不在合法范围内: {valid_values}")
        return False, error_message

    # ============================================================
    # 敏感信息规则
    # ============================================================

    def get_sensitive_patterns(self) -> list[tuple[str, str]]:
        """获取敏感信息模式列表

        Returns:
            (正则表达式, 类型名称) 元组列表
        """
        return list(self._get_cached_or_load("sensitive_patterns"))

    # ============================================================
    # 质量评分集成
    # ============================================================

    def _get_score_engine(self):
        """获取 TestCaseScoreEngine 实例（延迟导入）

        使用延迟导入避免与 test_case_strategy.py 产生循环依赖。
        """
        if self._score_engine is None:
            # 延迟导入
            from modules.trae_test.utils.test_case_strategy import TestCaseScoreEngine  # type: ignore[import-untyped]

            self._score_engine = TestCaseScoreEngine()
        return self._score_engine

    def score_test_case(self, case: dict[str, Any]) -> float:
        """对单条测试用例进行质量评分

        Args:
            case: 测试用例字典

        Returns:
            质量评分（0-100）
        """
        engine = self._get_score_engine()
        return engine.score(case)

    def score_contract(self, case: dict[str, Any]) -> dict[str, Any]:
        """返回审核侧使用的统一评分契约，不改变原有评分接口。"""
        engine = self._get_score_engine()
        metadata_fn = getattr(engine, "score_with_metadata", None)
        if callable(metadata_fn):
            metadata = dict(metadata_fn(case))
        else:
            execution_count = int(case.get("execution_count", 0) or 0)
            metadata = {
                "score": float(engine.score(case)),
                "is_cold_start": execution_count < COLD_START_EXECUTION_THRESHOLD,
                "confidence": min(execution_count / COLD_START_EXECUTION_THRESHOLD, 1.0),
            }
        # 15列模板中的“质量评分”是交付评分字段；若流程已写入最终评分，优先使用它。
        final_score = case.get("最终评分", case.get("质量评分"))
        if final_score not in (None, ""):
            metadata["score"] = float(final_score)
        metadata["threshold"] = FINAL_SCORE_THRESHOLD
        metadata["is_final_score_qualified"] = is_final_score_qualified(
            metadata["score"], is_cold_start=metadata["is_cold_start"]
        )
        return metadata

    def score_test_cases(self, cases: list[dict[str, Any]]) -> list[float]:
        """对多条测试用例进行批量质量评分

        Args:
            cases: 测试用例字典列表

        Returns:
            质量评分列表（顺序与输入一致）
        """
        engine = self._get_score_engine()
        return [engine.score(case) for case in cases]
