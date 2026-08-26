"""Phase 0 RAG retrieval recall evaluation.

Run:
    TEST_ENV=test python evaluation/phase0_rag_recall_eval.py

The default sample file is `evaluation/phase0_rag_sales_samples.json`.
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

from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
from modules.trae_test.utils.rag_semantic import SemanticConfig

DEFAULT_SAMPLES = Path("evaluation/phase0_rag_sales_samples.json")
DEFAULT_JSON_OUT = Path(".runtime/reports/harness_metrics/phase0_rag_eval.json")
DEFAULT_MD_OUT = Path(".runtime/reports/harness_metrics/phase0_rag_eval.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG hybrid retrieval Recall@K against a labeled sample set.")
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES, help="Labeled sample JSON file")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON_OUT, help="JSON report output path")
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD_OUT, help="Markdown summary output path")
    parser.add_argument("--top-k", type=int, default=5, help="Recall@K cutoff")
    parser.add_argument("--threshold", type=float, default=0.70, help="Go/no-go recall threshold")
    return parser.parse_args()


def load_samples(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        samples = json.load(f)
    if not isinstance(samples, list):
        raise ValueError(f"Sample file must contain a list: {path}")
    for index, sample in enumerate(samples, start=1):
        if not sample.get("query") or not sample.get("gold"):
            raise ValueError(f"Sample #{index} must include query and gold")
    return samples


def top_ids(results: Any, limit: int) -> list[str]:
    ids: list[str] = []
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                cid = item.get("chunk_id") or item.get("id")
                if cid:
                    ids.append(str(cid))
    return ids[:limit]


def recall(gold: set[str], ids: list[str]) -> float:
    if not gold:
        return 0.0
    return len(gold & set(ids)) / len(gold)


def auto_content_hit(auto_result: Any, keyphrase: str) -> bool:
    if auto_result is None or not keyphrase:
        return False
    blobs: list[str] = []
    if isinstance(auto_result, list):
        for item in auto_result:
            if isinstance(item, dict):
                blobs.append(" ".join(str(v) for v in item.values()))
    elif isinstance(auto_result, dict):
        blobs.append(" ".join(str(v) for v in auto_result.values()))
    return keyphrase in " ".join(blobs)


def evaluate(samples: list[dict[str, Any]], top_k: int, threshold: float) -> dict[str, Any]:
    os.environ.setdefault("TEST_ENV", "test")
    retriever = KnowledgeRetriever()
    semantic_config = SemanticConfig.from_env()

    rows: list[dict[str, Any]] = []
    hybrid_scores: list[float] = []
    lexical_scores: list[float] = []
    auto_hits: list[int] = []
    started = time.perf_counter()

    for sample in samples:
        query = str(sample["query"])
        gold = {str(item) for item in sample["gold"]}
        keyphrase = str(sample.get("keyphrase", ""))

        hybrid = retriever.retrieve(query, mode="hybrid")
        lexical = retriever.search_by_inverted_index(query, top_k=top_k)
        auto = retriever.retrieve(query, mode="auto")

        hybrid_ids = top_ids(hybrid, top_k)
        lexical_ids = top_ids(lexical, top_k)
        hybrid_recall = recall(gold, hybrid_ids)
        lexical_recall = recall(gold, lexical_ids)
        auto_hit = auto_content_hit(auto, keyphrase)

        hybrid_scores.append(hybrid_recall)
        lexical_scores.append(lexical_recall)
        auto_hits.append(1 if auto_hit else 0)
        rows.append(
            {
                "query": query,
                "gold": sorted(gold),
                f"hybrid_top{top_k}": hybrid_ids,
                f"hybrid_recall@{top_k}": round(hybrid_recall, 3),
                f"lexical_top{top_k}": lexical_ids,
                f"lexical_recall@{top_k}": round(lexical_recall, 3),
                "auto_return": type(auto).__name__,
                "auto_hit": auto_hit,
            }
        )

    sample_size = len(rows)
    hybrid_avg = sum(hybrid_scores) / sample_size
    lexical_avg = sum(lexical_scores) / sample_size
    auto_avg = sum(auto_hits) / sample_size

    return {
        "sample_size": sample_size,
        "top_k": top_k,
        f"hybrid_recall@{top_k}": round(hybrid_avg, 4),
        f"lexical_recall@{top_k}": round(lexical_avg, 4),
        "auto_content_hit_rate": round(auto_avg, 4),
        "delta_hybrid_minus_lexical": round(hybrid_avg - lexical_avg, 4),
        "gate_threshold": threshold,
        "gate_passed": hybrid_avg >= threshold,
        "embedding": {
            "provider": semantic_config.provider,
            "model_name": semantic_config.model_name,
            "vector_store_path": semantic_config.vector_store_path,
        },
        "duration_sec": round(time.perf_counter() - started, 3),
        "rows": rows,
    }


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    top_k = report["top_k"]
    status = "PASS" if report["gate_passed"] else "FAIL"
    content = f"""# Phase 0 RAG Retrieval Evaluation

## Summary

| Metric | Value |
|---|---:|
| Sample size | {report["sample_size"]} |
| Hybrid Recall@{top_k} | {report[f"hybrid_recall@{top_k}"]:.1%} |
| Lexical Recall@{top_k} | {report[f"lexical_recall@{top_k}"]:.1%} |
| Auto content hit rate | {report["auto_content_hit_rate"]:.1%} |
| Hybrid - Lexical | {report["delta_hybrid_minus_lexical"]:+.1%} |
| Gate threshold | {report["gate_threshold"]:.1%} |
| Gate | {status} |

## Embedding

- Provider: `{report["embedding"]["provider"]}`
- Model: `{report["embedding"]["model_name"]}`
- Vector store: `{report["embedding"]["vector_store_path"]}`

## Notes

This report covers retrieval recall only. LLM generation accuracy must be evaluated separately before releasing the generation path.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.ERROR)
    report = evaluate(load_samples(args.samples), top_k=args.top_k, threshold=args.threshold)
    write_json(args.out, report)
    write_markdown(args.markdown, report)

    top_k = report["top_k"]
    print("=" * 70)
    print("Phase 0 RAG PoC — Retrieval Recall Evaluation")
    print("=" * 70)
    print(f"样本数                : {report['sample_size']}")
    print(f"Hybrid  Recall@{top_k}     : {report[f'hybrid_recall@{top_k}']:.1%}")
    print(f"Lexical  Recall@{top_k}    : {report[f'lexical_recall@{top_k}']:.1%}")
    print(f"Auto 内容命中率       : {report['auto_content_hit_rate']:.1%}")
    print(f"Hybrid - Lexical      : {report['delta_hybrid_minus_lexical']:+.1%}")
    print(f"Gate                  : {'PASS' if report['gate_passed'] else 'FAIL'}")
    print("=" * 70)
    print(f"JSON 明细: {args.out}")
    print(f"Markdown 摘要: {args.markdown}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
