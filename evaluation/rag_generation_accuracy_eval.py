"""Evaluate RAG-backed test case generation accuracy.

Run:
    TEST_ENV=test python evaluation/rag_generation_accuracy_eval.py

This gate is intentionally local and deterministic: it evaluates the current
generation path against labeled RAG samples, then checks 15-field structure,
AuditGateway, TestCaseScoreEngine, and keyword grounding.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.trae_test.orchestrator.audit_gateway import AuditGateway
from modules.trae_test.orchestrator.config import AuditConfig, AuditType
from modules.trae_test.utils.template_builder import ALL_FIELDS
from modules.trae_test.utils.test_case_generator import TestCaseGenerator
from modules.trae_test.utils.test_case_strategy import TestCaseScoreEngine


DEFAULT_SAMPLES = Path("evaluation/phase0_rag_sales_samples.json")
DEFAULT_JSON_OUT = Path("reports/harness_metrics/rag_generation_accuracy_eval.json")
DEFAULT_MD_OUT = Path("reports/harness_metrics/rag_generation_accuracy_eval.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG generation accuracy against labeled samples.")
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES, help="Labeled sample JSON file")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON_OUT, help="JSON report output path")
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD_OUT, help="Markdown summary output path")
    parser.add_argument("--threshold", type=float, default=0.60, help="Go/no-go accuracy threshold")
    parser.add_argument("--limit", type=int, default=3, help="Generated candidate cases per sample")
    parser.add_argument("--min-score", type=float, default=60.0, help="Minimum TestCaseScoreEngine score")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit samples for a smoke run; 0 means all")
    return parser.parse_args()


def load_samples(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        samples = json.load(f)
    if not isinstance(samples, list):
        raise ValueError(f"Sample file must contain a list: {path}")
    for index, sample in enumerate(samples, start=1):
        if not sample.get("query"):
            raise ValueError(f"Sample #{index} must include query")
    return samples


def text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(text_blob(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(text_blob(item) for item in value)
    return "" if value is None else str(value)


def field_completeness(case: dict[str, Any]) -> tuple[float, list[str]]:
    missing = [field for field in ALL_FIELDS if field not in case]
    present_count = len(ALL_FIELDS) - len(missing)
    return present_count / len(ALL_FIELDS), missing


def required_keyphrase_hit(case: dict[str, Any], sample: dict[str, Any]) -> bool:
    keyphrase = str(sample.get("keyphrase", "")).strip()
    if not keyphrase:
        return True
    return keyphrase in text_blob(case)


def evaluate_case(
    case: dict[str, Any],
    sample: dict[str, Any],
    score_engine: TestCaseScoreEngine,
    gateway: AuditGateway,
    min_score: float,
) -> dict[str, Any]:
    completeness, missing_fields = field_completeness(case)
    score = score_engine.score(case)
    audit = gateway.audit([case], AuditType.TEST_CASE, {"block_on_fail": False})
    keyphrase_hit = required_keyphrase_hit(case, sample)
    passed = completeness >= 1.0 and audit.passed and score >= min_score and keyphrase_hit

    return {
        "case_name": str(case.get(ALL_FIELDS[1], "")),
        "field_completeness": round(completeness, 4),
        "missing_fields": missing_fields,
        "score": score,
        "audit_passed": audit.passed,
        "audit_errors": len(audit.errors),
        "audit_warnings": len(audit.warnings),
        "keyphrase": str(sample.get("keyphrase", "")),
        "keyphrase_hit": keyphrase_hit,
        "passed": passed,
    }


def evaluate(samples: list[dict[str, Any]], threshold: float, limit: int, min_score: float) -> dict[str, Any]:
    os.environ.setdefault("TEST_ENV", "test")
    generator = TestCaseGenerator()
    score_engine = TestCaseScoreEngine()
    gateway = AuditGateway(AuditConfig(interactive_mode=False, auto_approve=True))

    rows: list[dict[str, Any]] = []
    passed_count = 0
    generated_count = 0
    started = time.perf_counter()

    for sample in samples:
        query = str(sample["query"])
        cases = generator.generate_cases(query, limit=limit)
        generated_count += len(cases)
        case_results = [
            evaluate_case(case, sample, score_engine=score_engine, gateway=gateway, min_score=min_score)
            for case in cases
        ]
        sample_passed = bool(case_results) and any(item["passed"] for item in case_results)
        if sample_passed:
            passed_count += 1
        rows.append(
            {
                "query": query,
                "generated_cases": len(cases),
                "passed": sample_passed,
                "cases": case_results,
            }
        )

    sample_size = len(samples)
    accuracy = passed_count / sample_size if sample_size else 0.0
    return {
        "sample_size": sample_size,
        "generated_cases": generated_count,
        "passed_samples": passed_count,
        "generation_accuracy": round(accuracy, 4),
        "gate_threshold": threshold,
        "gate_passed": accuracy >= threshold,
        "min_score": min_score,
        "field_count": len(ALL_FIELDS),
        "duration_sec": round(time.perf_counter() - started, 3),
        "rows": rows,
    }


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    status = "PASS" if report["gate_passed"] else "FAIL"
    content = f"""# RAG Generation Accuracy Evaluation

## Summary

| Metric | Value |
|---|---:|
| Sample size | {report["sample_size"]} |
| Generated cases | {report["generated_cases"]} |
| Passed samples | {report["passed_samples"]} |
| Generation accuracy | {report["generation_accuracy"]:.1%} |
| Gate threshold | {report["gate_threshold"]:.1%} |
| Minimum score | {report["min_score"]:.1f} |
| 15-field count | {report["field_count"]} |
| Gate | {status} |

## Gate Rules

- Each sample must generate at least one case.
- At least one candidate case must pass all checks for each sample.
- The passing candidate must include all 15 standard fields.
- AuditGateway test-case audit must pass for the candidate.
- TestCaseScoreEngine score must be at least the configured minimum.
- If the sample provides a keyphrase, it must appear in the candidate case.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.ERROR)
    samples = load_samples(args.samples)
    if args.max_samples:
        samples = samples[: args.max_samples]
    report = evaluate(samples, threshold=args.threshold, limit=args.limit, min_score=args.min_score)
    write_json(args.out, report)
    write_markdown(args.markdown, report)

    print("=" * 70)
    print("RAG Generation Accuracy Evaluation")
    print("=" * 70)
    print(f"Sample size          : {report['sample_size']}")
    print(f"Generated cases      : {report['generated_cases']}")
    print(f"Passed samples       : {report['passed_samples']}")
    print(f"Generation accuracy  : {report['generation_accuracy']:.1%}")
    print(f"Gate                 : {'PASS' if report['gate_passed'] else 'FAIL'}")
    print("=" * 70)
    print(f"JSON detail          : {args.out}")
    print(f"Markdown summary     : {args.markdown}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
