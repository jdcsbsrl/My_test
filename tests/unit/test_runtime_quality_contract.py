from modules.trae_test.utils.runtime_quality import (
    QUALITY_SCORE_THRESHOLD,
    RUNTIME_QUALITY_KEY,
    RUNTIME_QUALITY_VERSION_KEY,
    RuntimeQualitySnapshot,
    attach_runtime_quality,
    read_runtime_quality,
)
from modules.trae_test.utils.template_builder import ALL_FIELDS


def test_runtime_quality_has_explicit_85_gate_and_history() -> None:
    snapshot = RuntimeQualitySnapshot(
        original_score=62,
        optimized_score=86,
        final_score=86,
        score_history=[{"stage": "original", "score": 62}],
        is_cold_start=True,
        confidence=0.2,
        optimization_attempts=1,
        final_audit_passed=True,
    )

    assert QUALITY_SCORE_THRESHOLD == 85.0
    assert snapshot.to_dict()["final_score"] == 86
    assert snapshot.to_dict()["score_history"]


def test_runtime_quality_is_nested_and_does_not_extend_formal_15_fields() -> None:
    case = {field: "" for field in ALL_FIELDS}
    attach_runtime_quality(case, RuntimeQualitySnapshot(final_score=90, final_audit_passed=True))

    assert list(field for field in case if not field.startswith("_runtime_")) == ALL_FIELDS
    assert case[RUNTIME_QUALITY_VERSION_KEY] == "1.0"
    assert case[RUNTIME_QUALITY_KEY]["final_score"] == 90


def test_runtime_quality_round_trip_and_missing_value() -> None:
    case = {}
    attach_runtime_quality(case, {"final_score": 85, "needs_human_review": False})

    restored = read_runtime_quality(case)
    assert restored.final_score == 85
    assert restored.needs_human_review is False
    assert read_runtime_quality({}).final_score is None
