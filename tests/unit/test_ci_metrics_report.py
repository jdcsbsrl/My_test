import tools.generate_ci_metrics_report as metrics_report


def test_failure_evidence_ignores_setup_keywords_and_deduplicates_pytest_summary():
    logs = "\n".join(
        [
            "pip install playwright pytest",
            "2026-09-16T00:00:00Z test.py::test_one FAILED [100%]",
            "2026-09-16T00:00:01Z FAILED test.py::test_one - AssertionError: expected data",
            "2026-09-16T00:00:01Z E   AssertionError: expected data",
        ]
    )

    evidence = metrics_report._failure_evidence(logs)

    assert evidence == "AssertionError: expected data"


def test_build_metrics_counts_categories_from_failed_tests_only():
    jobs = [{"id": 1, "status": "completed", "conclusion": "failure", "steps": []}]
    logs = "\n".join(
        [
            "Installing pip install playwright",
            "FAILED tests/test_example.py::test_timeout - TimeoutError: timed out",
            "E   TimeoutError: timed out",
        ]
    )

    metrics = metrics_report.build_metrics(jobs, logs, "example/repo", "123")

    assert metrics["error_category_counts"] == {"超时": 1}
