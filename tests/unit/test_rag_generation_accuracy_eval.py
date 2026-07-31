from types import SimpleNamespace

import evaluation.rag_generation_accuracy_eval as rag_eval
from modules.trae_test.utils.template_builder import ALL_FIELDS


def _complete_case(**overrides):
    case = {field: f"value-{index}" for index, field in enumerate(ALL_FIELDS, start=1)}
    case.update(overrides)
    return case


class _FakeScoreEngine:
    def score(self, case):
        return case.get("_score", 80.0)


class _FakeGateway:
    def __init__(self, passed=True):
        self.passed = passed

    def audit(self, target, audit_type, context):
        return SimpleNamespace(passed=self.passed, errors=[], warnings=[])


def test_field_completeness_requires_all_15_fields():
    case = _complete_case()
    completeness, missing = rag_eval.field_completeness(case)

    assert completeness == 1.0
    assert missing == []

    case.pop(ALL_FIELDS[0])
    completeness, missing = rag_eval.field_completeness(case)

    assert completeness < 1.0
    assert missing == [ALL_FIELDS[0]]


def test_evaluate_case_requires_score_audit_and_keyphrase():
    case = _complete_case(**{ALL_FIELDS[4]: "step includes expected keyphrase"})
    sample = {"query": "demo", "keyphrase": "expected keyphrase"}

    passed = rag_eval.evaluate_case(
        case,
        sample,
        score_engine=_FakeScoreEngine(),
        gateway=_FakeGateway(passed=True),
        min_score=60.0,
    )

    assert passed["passed"] is True
    assert passed["field_completeness"] == 1.0
    assert passed["keyphrase_hit"] is True

    failed = rag_eval.evaluate_case(
        _complete_case(_score=50.0),
        sample,
        score_engine=_FakeScoreEngine(),
        gateway=_FakeGateway(passed=True),
        min_score=60.0,
    )

    assert failed["passed"] is False
    assert failed["score"] == 50.0


def test_evaluate_computes_generation_accuracy(monkeypatch):
    class FakeGenerator:
        def generate_cases(self, keyword, limit=1):
            if keyword == "missing":
                return []
            return [_complete_case(**{ALL_FIELDS[4]: f"step {keyword}"})]

    monkeypatch.setattr(rag_eval, "TestCaseGenerator", lambda: FakeGenerator())
    monkeypatch.setattr(rag_eval, "TestCaseScoreEngine", lambda: _FakeScoreEngine())
    monkeypatch.setattr(rag_eval, "AuditGateway", lambda config: _FakeGateway(passed=True))

    report = rag_eval.evaluate(
        [
            {"query": "alpha", "keyphrase": "alpha"},
            {"query": "missing", "keyphrase": "missing"},
        ],
        threshold=0.60,
        limit=1,
        min_score=60.0,
    )

    assert report["sample_size"] == 2
    assert report["generated_cases"] == 1
    assert report["passed_samples"] == 1
    assert report["generation_accuracy"] == 0.5
    assert report["gate_passed"] is False
