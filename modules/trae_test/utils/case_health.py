"""Read-only maintenance signals; never retire cases based on heuristics."""

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path


def case_health(registry, requirement_id=None, *, stale_days=30) -> dict:
    from modules.auto_test.core.registered_regression import validate_script_node

    if stale_days <= 0:
        raise ValueError("stale_days must be positive")
    rows = registry.list_cases(requirement_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    issues, similar = [], []
    for row in rows:
        signals = []
        if not row["last_status"]:
            signals.append("never_executed")
        elif row["last_status"] != "PASS":
            signals.append("last_execution_not_passed")
        if row.get("last_evidence") and not Path(row["last_evidence"]).is_file():
            signals.append("execution_evidence_missing")
        if row.get("last_executed_at") and datetime.fromisoformat(row["last_executed_at"]) < cutoff:
            signals.append("stale_execution")
        if not row["script_id"]:
            signals.append("unbound_script")
        else:
            try:
                validate_script_node(row["script_id"])
            except (ValueError, OSError):
                signals.append("invalid_script")
            if not row.get("script_digest"):
                signals.append("script_snapshot_missing")
            elif row["script_digest"] != registry.script_digest(row["script_id"]):
                signals.append("script_changed")
        if signals:
            issues.append({"case_id": row["case_id"], "version": row["version"], "signals": signals})
    # Compare within a requirement only; this is a review suggestion, not semantic equivalence.
    for index, row in enumerate(rows):
        content = "\n".join(str(row["content"].get(k, "")) for k in ("前置条件", "用例步骤", "预期结果"))
        for other in rows[index + 1 :]:
            if row["requirement_id"] != other["requirement_id"]:
                continue
            first_binding = row["content"].get("_runtime_rule_binding", {})
            second_binding = other["content"].get("_runtime_rule_binding", {})
            if (
                first_binding
                and second_binding
                and any(first_binding.get(k) != second_binding.get(k) for k in ("source_id", "rule_id", "scenario"))
            ):
                continue
            candidate = "\n".join(str(other["content"].get(k, "")) for k in ("前置条件", "用例步骤", "预期结果"))
            ratio = SequenceMatcher(None, content, candidate, autojunk=False).ratio()
            if ratio >= 0.9:
                similar.append({"case_ids": [row["case_id"], other["case_id"]], "text_similarity": round(ratio, 3)})
    return {"active_count": len(rows), "issues": issues, "similar_candidates": similar}
