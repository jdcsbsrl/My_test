"""Automatic delivery gate for audited test-case and regression results.

The structural score is intentionally advisory.  Delivery is decided from
business audit, priority coverage and trustworthy execution evidence instead
of from a single synthetic score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

READY_FOR_DELIVERY = "READY_FOR_DELIVERY"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
BLOCKED = "BLOCKED"
INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class ReleaseDecision:
    """Machine-readable release decision shared by generation and regression."""

    status: str
    can_deliver: bool
    blocking_issues: tuple[dict[str, str], ...] = field(default_factory=tuple)
    warnings: tuple[dict[str, str], ...] = field(default_factory=tuple)
    required_review: tuple[dict[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "can_deliver": self.can_deliver,
            "blocking_issues": list(self.blocking_issues),
            "warnings": list(self.warnings),
            "required_review": list(self.required_review),
        }


class ReleaseQualityGate:
    """Evaluate release readiness without modifying cases or reports."""

    def evaluate(
        self,
        *,
        cases: Iterable[Mapping[str, Any]] = (),
        audit_result: Any = None,
        regression_report: Any = None,
        release_scope: str = "generation",
        require_regression: bool | None = None,
        require_p0: bool | None = None,
        require_cases: bool = True,
    ) -> ReleaseDecision:
        if release_scope not in {"generation", "smoke", "module", "release"}:
            raise ValueError("Unsupported release scope")
        case_list = list(cases)
        blocking: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        review: list[dict[str, str]] = []

        self._audit_issues(audit_result, blocking)
        if require_cases:
            self._case_signals(case_list, blocking, warnings, review)

        must_regress = require_regression if require_regression is not None else release_scope != "generation"
        must_cover_p0 = require_p0 if require_p0 is not None else release_scope == "release"
        if must_cover_p0 and not any(str(case.get("优先级", "")).upper() == "P0" for case in case_list):
            blocking.append({"code": "P0_NOT_PRESENT", "message": "Release scope must include at least one P0 case"})
        if must_regress:
            self._regression_signals(regression_report, case_list, blocking, warnings, review)
        elif regression_report is not None:
            self._regression_signals(regression_report, case_list, blocking, warnings, review)

        if blocking:
            status = BLOCKED
        elif review:
            status = REQUIRES_REVIEW
        elif must_regress and regression_report is None:
            status = INCOMPLETE
        else:
            status = READY_FOR_DELIVERY
        return ReleaseDecision(
            status=status,
            can_deliver=status == READY_FOR_DELIVERY,
            blocking_issues=tuple(blocking),
            warnings=tuple(warnings),
            required_review=tuple(review),
        )

    @staticmethod
    def _audit_issues(audit_result: Any, blocking: list[dict[str, str]]) -> None:
        if audit_result is None:
            return
        if isinstance(audit_result, Mapping):
            errors = audit_result.get("errors", [])
        else:
            errors = getattr(audit_result, "errors", [])
        passed = (
            audit_result.get("passed") if isinstance(audit_result, Mapping) else getattr(audit_result, "passed", None)
        )
        if passed is False and not errors:
            blocking.append({"code": "AUDIT_FAILED", "message": "AuditAgent did not approve the target"})
        for error in errors or []:
            if isinstance(error, Mapping):
                blocking.append(
                    {
                        "code": str(error.get("code", "AUDIT_ERROR")),
                        "message": str(error.get("message", "AuditAgent reported an error")),
                    }
                )
            else:
                blocking.append({"code": "AUDIT_ERROR", "message": str(error)})

    @staticmethod
    def _case_signals(
        cases: list[Mapping[str, Any]],
        blocking: list[dict[str, str]],
        warnings: list[dict[str, str]],
        review: list[dict[str, str]],
    ) -> None:
        if not cases:
            blocking.append({"code": "NO_CASES", "message": "No test cases are available for delivery"})
            return
        p0_cases = [case for case in cases if str(case.get("优先级", "")).upper() == "P0"]
        for index, case in enumerate(cases, 1):
            quality = case.get("_runtime_quality")
            if not isinstance(quality, Mapping):
                blocking.append({"code": "QUALITY_MISSING", "message": f"Case {index} has no runtime audit quality"})
            elif quality.get("final_audit_passed") is not True:
                blocking.append({"code": "CASE_AUDIT_FAILED", "message": f"Case {index} did not pass final audit"})
            score = case.get("质量评分")
            if score is not None:
                try:
                    if float(score) < 85:
                        warnings.append(
                            {"code": "STRUCTURAL_SCORE_LOW", "message": f"Case {index} structural score is below 85"}
                        )
                except (TypeError, ValueError):
                    blocking.append(
                        {"code": "QUALITY_INVALID", "message": f"Case {index} has an invalid structural score"}
                    )
            if quality and quality.get("needs_human_review"):
                review.append({"code": "CASE_REQUIRES_REVIEW", "message": f"Case {index} is marked for human review"})
            if case.get("_runtime_rule_binding") is None and str(case.get("知识库关联", "")).strip() == "":
                blocking.append({"code": "EVIDENCE_MISSING", "message": f"Case {index} has no business evidence"})
        if not p0_cases:
            warnings.append({"code": "P0_NOT_PRESENT", "message": "No P0 case is included in this delivery set"})

    @staticmethod
    def _regression_signals(
        report: Any,
        cases: list[Mapping[str, Any]],
        blocking: list[dict[str, str]],
        warnings: list[dict[str, str]],
        review: list[dict[str, str]],
    ) -> None:
        if report is None:
            return
        results = report.get("results", []) if isinstance(report, Mapping) else getattr(report, "results", [])
        planned = report.get("planned", 0) if isinstance(report, Mapping) else getattr(report, "planned_count", 0)
        if not results or (planned and len(results) < planned):
            blocking.append({"code": "REGRESSION_INCOMPLETE", "message": "Regression evidence is incomplete"})
        for result in results or []:
            status = str(result.get("status", "")) if isinstance(result, Mapping) else ""
            name = str(result.get("test_name", "unknown")) if isinstance(result, Mapping) else "unknown"
            if status == "FAIL":
                blocking.append({"code": "REGRESSION_FAILED", "message": f"Regression failed: {name}"})
            elif status in {"BLOCKED", "SKIP"}:
                review.append({"code": "REGRESSION_NOT_VERIFIED", "message": f"Regression not fully verified: {name}"})
        if any(str(case.get("优先级", "")).upper() == "P0" for case in cases):
            p0_names = {
                identifier
                for case in cases
                if str(case.get("优先级", "")).upper() == "P0"
                for identifier in (str(case.get("_registered_name") or case.get("用例名称", "")),)
                if identifier
            }
            result_names = {str(result.get("test_name", "")) for result in results if isinstance(result, Mapping)}
            missing = sorted(
                name
                for name in p0_names
                if name not in result_names
                and not any(
                    name == result_name or name in result_name or result_name in name for result_name in result_names
                )
            )
            if missing:
                blocking.append(
                    {
                        "code": "P0_NOT_EXECUTED",
                        "message": "P0 cases lack matching regression evidence: " + ", ".join(missing),
                    }
                )
