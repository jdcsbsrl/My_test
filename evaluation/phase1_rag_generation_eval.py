"""Phase 1 RAG generation accuracy evaluation.

This harness evaluates the generation gate before the RAG generation path is
released. The default provider is local and deterministic; a self-hosted LLM
provider can replace it later without changing the reporting contract.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.trae_test.utils.rag_generation import RAGGenerationEvaluator, build_rag_case_generator

DEFAULT_SAMPLES = Path("evaluation/phase1_rag_generation_samples.json")
DEFAULT_JSON_OUT = Path(".runtime/reports/harness_metrics/phase1_rag_generation_eval.json")
DEFAULT_MD_OUT = Path(".runtime/reports/harness_metrics/phase1_rag_generation_eval.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG generation accuracy against expected case points.")
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES, help="Generation sample JSON file")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON_OUT, help="JSON report output path")
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD_OUT, help="Markdown summary output path")
    parser.add_argument("--threshold", type=float, default=0.60, help="Generation pass-rate gate")
    parser.add_argument("--point-threshold", type=float, default=0.60, help="Per-case expected-point hit threshold")
    parser.add_argument("--score-threshold", type=float, default=50.0, help="Per-case TestCaseScoreEngine threshold")
    parser.add_argument(
        "--provider",
        choices=["local-rule", "self-hosted-llm"],
        default="local-rule",
        help="Generation provider to evaluate",
    )
    return parser.parse_args()


def load_samples(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        samples = json.load(f)
    if not isinstance(samples, list):
        raise ValueError(f"Sample file must contain a list: {path}")
    for index, sample in enumerate(samples, start=1):
        if not sample.get("query") or not sample.get("expected_points"):
            raise ValueError(f"Sample #{index} must include query and expected_points")
    return samples


def evaluate(
    samples: list[dict[str, Any]],
    threshold: float,
    point_threshold: float,
    score_threshold: float,
    provider: str,
) -> dict[str, Any]:
    os.environ.setdefault("TEST_ENV", "test")
    generator = build_rag_case_generator(provider)
    evaluator = RAGGenerationEvaluator(
        generator=generator,
        point_threshold=point_threshold,
        score_threshold=score_threshold,
    )
    started = time.perf_counter()

    rows = []
    for sample in samples:
        result = evaluator.evaluate_one(
            query=str(sample["query"]),
            expected_points=[str(item) for item in sample["expected_points"]],
        )
        rows.append(asdict(result))

    sample_size = len(rows)
    passed_count = sum(1 for row in rows if row["passed"])
    audit_passed_count = sum(1 for row in rows if row["audit_passed"])
    avg_point_hit = sum(row["point_hit_rate"] for row in rows) / sample_size
    avg_score = sum(row["quality_score"] for row in rows) / sample_size
    accuracy = passed_count / sample_size

    return {
        "sample_size": sample_size,
        "generation_accuracy": round(accuracy, 4),
        "gate_threshold": threshold,
        "gate_passed": accuracy >= threshold,
        "passed_count": passed_count,
        "audit_passed_count": audit_passed_count,
        "avg_point_hit_rate": round(avg_point_hit, 4),
        "avg_quality_score": round(avg_score, 2),
        "point_threshold": point_threshold,
        "score_threshold": score_threshold,
        "provider": generator.provider_name,
        "llm_api_style": getattr(getattr(generator, "api_style", ""), "value", ""),
        "llm_model": getattr(generator, "model", ""),
        "duration_sec": round(time.perf_counter() - started, 3),
        "rows": rows,
    }


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    status = "PASS" if report["gate_passed"] else "FAIL"
    content = f"""# Phase 1 RAG Generation Evaluation

## Summary

| Metric | Value |
|---|---:|
| Sample size | {report["sample_size"]} |
| Generation accuracy | {report["generation_accuracy"]:.1%} |
| Gate threshold | {report["gate_threshold"]:.1%} |
| Gate | {status} |
| Passed cases | {report["passed_count"]} |
| Audit passed cases | {report["audit_passed_count"]} |
| Avg expected-point hit rate | {report["avg_point_hit_rate"]:.1%} |
| Avg quality score | {report["avg_quality_score"]:.2f} |

## Provider

- Provider: `{report["provider"]}`
- LLM API style: `{report["llm_api_style"]}`
- LLM model: `{report["llm_model"]}`
- Per-case expected-point threshold: `{report["point_threshold"]}`
- Per-case quality score threshold: `{report["score_threshold"]}`

## Notes

This is the generation gate harness. The current provider is deterministic
and local. A self-hosted LLM provider must be evaluated with the same report
contract before release.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.ERROR)
    report = evaluate(
        load_samples(args.samples),
        args.threshold,
        args.point_threshold,
        args.score_threshold,
        args.provider,
    )
    write_json(args.out, report)
    write_markdown(args.markdown, report)

    print("=" * 70)
    print("Phase 1 RAG — Generation Accuracy Evaluation")
    print("=" * 70)
    print(f"样本数              : {report['sample_size']}")
    print(f"Generation accuracy : {report['generation_accuracy']:.1%}")
    print(f"Audit passed         : {report['audit_passed_count']}/{report['sample_size']}")
    print(f"Avg point hit rate   : {report['avg_point_hit_rate']:.1%}")
    print(f"Avg quality score    : {report['avg_quality_score']:.2f}")
    print(f"Gate                 : {'PASS' if report['gate_passed'] else 'FAIL'}")
    print("=" * 70)
    print(f"JSON 明细: {args.out}")
    print(f"Markdown 摘要: {args.markdown}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
