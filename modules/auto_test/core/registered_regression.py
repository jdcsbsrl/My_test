"""Resolve active case versions into an explicit, reviewable pytest selection."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

from modules.trae_test.utils.runtime_paths import project_root, runtime_dir


def validate_script_node(script: str) -> None:
    root = project_root()
    filename, separator, node = script.partition("::")
    path = (root / filename).resolve()
    allowed = (root / "modules/auto_test/tests").resolve()
    if (
        not separator
        or not node
        or not path.is_relative_to(allowed)
        or path.suffix != ".py"
        or not path.is_file()
        or any(c in script for c in ("\n", "\r"))
    ):
        raise ValueError("A valid module pytest node ID is required")
    try:
        body = ast.parse(path.read_text(encoding="utf-8-sig")).body
        parts = node.split("[", 1)[0].split("::")
        for index, part in enumerate(parts):
            target = next(
                (
                    item
                    for item in body
                    if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == part
                ),
                None,
            )
            if target is None:
                raise ValueError("Registered pytest node no longer exists")
            if index == len(parts) - 1 and (
                not isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)) or not part.startswith("test_")
            ):
                raise ValueError("Bind a test function, not a class or module")
            body = target.body
    except SyntaxError as exc:
        raise ValueError("Registered test script has invalid syntax") from exc


def plan_registered_cases(registry, case_ids: list[str]) -> list[dict]:
    active = registry.list_cases()
    by_id = {row["case_id"]: row for row in active}
    if not case_ids or any(case_id not in by_id for case_id in case_ids):
        raise ValueError("Select existing active case IDs")
    selected = [by_id[case_id] for case_id in dict.fromkeys(case_ids)]
    requirements = {row["requirement_id"] for row in selected}
    related_p0 = [
        row["case_id"]
        for row in active
        if row["requirement_id"] in requirements
        and row["content"].get("优先级") == "P0"
        and row["case_id"] not in case_ids
    ]
    # P0 cases are added automatically so a caller cannot accidentally narrow
    # a run past the core safety boundary. Keep the caller's order first, then
    # append deterministic related P0 cases for a reviewable plan.
    selected.extend(by_id[case_id] for case_id in related_p0)
    for row in selected:
        validate_script_node(row["script_id"])
        if row.get("script_digest") and row["script_digest"] != registry.script_digest(row["script_id"]):
            raise ValueError(f"Case {row['case_id']} script changed; review and bind a new version")
    return selected


def run_registered_cases(registry, selected: list[dict], env_name: str) -> int:
    from .config_manager import get_environment
    from .execution_auth import check_authorization
    from tools.report_generator import TestReportGenerator
    from modules.trae_test.orchestrator.release_quality_gate import ReleaseQualityGate

    if env_name not in {"test", "uat"}:
        raise ValueError("Only test/uat are allowed")
    check_authorization()
    get_environment(env_name)
    run_id = uuid.uuid4().hex
    root = runtime_dir("reports") / "registered" / run_id
    root.mkdir(parents=True, exist_ok=True)
    report = TestReportGenerator()
    report.planned_count = len(selected)
    for row in selected:
        evidence = root / f"{row['case_id']}_v{row['version']}.xml"
        env = {**os.environ, "TEST_ENV": env_name, "TEST_RUN_ID": f"{run_id}-{row['case_id']}"}
        command = [sys.executable, "-m", "pytest", row["script_id"], f"--junitxml={evidence}", "--tb=short"]
        status = "BLOCKED"
        detail = "Execution did not produce complete passing evidence"
        try:
            with evidence.with_suffix(".log").open("w", encoding="utf-8") as stream:
                completed = subprocess.run(
                    command,
                    cwd=project_root(),
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=600,
                )
            if evidence.exists():
                tree = ET.parse(evidence)
                nodes = list(tree.iter("testcase"))
                if list(tree.iter("failure")) or list(tree.iter("error")):
                    status = "FAIL"
                elif nodes and completed.returncode == 0 and not list(tree.iter("skipped")):
                    status, detail = "PASS", "Selected pytest node passed"
        except (ET.ParseError, OSError, subprocess.TimeoutExpired) as exc:
            detail = type(exc).__name__
        proof = evidence if evidence.exists() else evidence.with_suffix(".log")
        registry.record_execution(row["case_id"], row["version"], status, str(proof))
        report.add_test_result(f"{row['case_id']} v{row['version']}", status, f"{detail}; evidence={proof}")
    gate_cases = []
    for row in selected:
        content = row.get("content") or {}
        if not content:
            continue
        case = dict(content)
        case["_registered_name"] = f"{row['case_id']} v{row['version']}"
        gate_cases.append(case)
    decision = ReleaseQualityGate().evaluate(
        cases=gate_cases,
        regression_report=report,
        release_scope="module",
        require_regression=True,
        require_cases=bool(gate_cases),
    )
    report.release_decision = decision.to_dict()
    report.generate_json_report(str(root / "summary.json"))
    report.generate_html_report(str(root / "summary.html"))
    print(f"登记用例执行报告: {root / 'summary.html'}")
    return 1 if decision.status == "BLOCKED" else 2 if not decision.can_deliver else 0
