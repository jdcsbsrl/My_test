"""Finite rule contracts from retrieval results; not a natural-language theorem prover."""

import hashlib
import json


def digest_rule(rule):
    return hashlib.sha256(json.dumps(rule, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source_rules(sources):
    rules = {}
    for source in sources or []:
        content = source.get("content", {})
        if not isinstance(content, dict):
            continue
        for rule in content.get("query_contracts", []):
            key = (source.get("id") or source.get("chunk_id"), rule.get("id"))
            if key in rules:
                raise ValueError("Duplicate rule identity in retrieved sources")
            rules[key] = rule
    return rules


def validate_binding(binding):
    if not isinstance(binding, dict):
        raise ValueError("Rule binding must be an object")
    for key in ("source_id", "rule_id", "revision", "scenario"):
        if not isinstance(binding.get(key), str) or not binding[key].strip():
            raise ValueError(f"Rule binding requires {key}")


def validate_assertions(predicates):
    if not isinstance(predicates, list) or not predicates:
        raise ValueError("Rule requires executable assertions")
    for item in predicates:
        if not isinstance(item, dict) or set(item) != {"field", "op", "value"}:
            raise ValueError("Assertion must contain field, op and value only")
        field, op, value = item["field"], item["op"], item["value"]
        if op == "count_range" and field == "rows":
            if (
                not isinstance(value, list)
                or len(value) != 2
                or any(type(v) is not int or v < 0 for v in value)
                or value[0] > value[1]
            ):
                raise ValueError("Invalid count range")
        elif op == "eq" and field in {"orderNo", "orderStatus"}:
            if type(value) not in {str, int} or value == "":
                raise ValueError("Invalid equality value")
        elif op == "contains" and field in {"orderNo", "orderStatus", "sku"}:
            if not isinstance(value, str) or not value:
                raise ValueError("Invalid contains value")
        elif op == "disjoint" and field == "orderNo" and value == "next_page":
            continue
        else:
            raise ValueError("Unsupported predicate; semantic verification incomplete")


def evaluate_assertions(rows, predicates, *, next_rows=None):
    """Execute the supported contracts against already parsed order responses."""
    validate_assertions(predicates)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Expected order rows")
    for item in predicates:
        field, op, value = item["field"], item["op"], item["value"]
        if op == "count_range":
            assert value[0] <= len(rows) <= value[1], "Record count contradicts rule"
        elif op == "eq":
            assert rows and all(
                field in row and str(row[field]) == str(value) for row in rows
            ), "Field contradicts rule"
        elif op == "contains":
            assert rows and all(
                field in row and str(value) in str(row[field]) for row in rows
            ), "Field does not contain required value"
        else:
            assert rows and next_rows and all(row.get(field) for row in rows + next_rows), "Missing pagination evidence"
            assert {row[field] for row in rows}.isdisjoint(row[field] for row in next_rows), "Pages overlap"


def check_contract(case, sources, result):
    """Fail closed on known contracts, and return a verified dependency snapshot."""
    binding = case.get("_runtime_rule_binding")
    try:
        rules = source_rules(sources)
        if not binding and not rules:
            return None
        validate_binding(binding)
        rule = rules.get((binding["source_id"], binding["rule_id"]))
        if not rule:
            raise ValueError("Referenced rule is absent from retrieved sources")
        if rule.get("revision") != binding["revision"] or rule.get("scenario") != binding["scenario"]:
            raise ValueError("Rule revision or scenario does not match source")
        predicates = rule.get("assertions")
        validate_assertions(predicates)
        if binding.get("assertions", predicates) != predicates:
            raise ValueError("Candidate assertions contradict the retrieved rule")
        # A finite contract supplies reviewed wording; paraphrases are not silently accepted.
        if case.get("预期结果", "").strip() != str(rule.get("expected_text", "")).strip():
            raise ValueError("Expected result does not match the retrieved rule contract")
        matrix = case.get("_runtime_coverage_matrix") or {}
        if binding["rule_id"] not in matrix.get("business_rules", []):
            raise ValueError("Required rule is absent from case coverage")
        return {**binding, "digest": digest_rule(rule), "object": rule.get("object", ""), "assertions": predicates}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        result.add_error("TC_RULE_CONTRACT", str(exc), "规则与预期映射")
        return None


def impact_plan(registry, sources, requirement_id=None):
    current = source_rules(sources)
    affected, unknown = [], []
    active = registry.list_cases(requirement_id)
    for row in active:
        binding = row["content"].get("_runtime_rule_binding")
        if not binding:
            unknown.append(row["case_id"])
            continue
        rule = current.get((binding["source_id"], binding["rule_id"]))
        # Caller must supply the complete relevant source snapshot; absence is not 'unchanged'.
        if not rule or digest_rule(rule) != binding.get("digest"):
            affected.append({"case_id": row["case_id"], "reason": "rule_missing" if not rule else "rule_changed"})
    requirements = {row["requirement_id"] for row in active if row["case_id"] in {r["case_id"] for r in affected}}
    selected = {row["case_id"] for row in affected}
    selected.update(
        row["case_id"]
        for row in active
        if row["requirement_id"] in requirements and row["content"].get("优先级") == "P0"
    )
    return {"affected": affected, "selected_case_ids": sorted(selected), "unverified_case_ids": unknown}
