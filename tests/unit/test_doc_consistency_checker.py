from pathlib import Path

from tools.doc_consistency_checker import DocConsistencyChecker


def write_core_docs(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    for relative_path in (
        "TRAE_TEST_WORKFLOW.md",
        "AUTO_TEST_WORKFLOW.md",
        "LOCAL_KNOWLEDGE_BASE_GUIDE.md",
        "KNOWLEDGE_BASE_UPDATE_WORKFLOW.md",
        "KNOWLEDGE_BASE_RETRIEVER.md",
        "ARCHITECTURE.md",
        "CODING_RULES.md",
        "PROJECT_ARTIFACT_PLACEMENT.md",
        "AGENT_RULES.md",
    ):
        (root / "docs" / relative_path).write_text(
            "---\ntitle: test\npurpose: test\nversion: 1.0.0\nupdated: 2026-08-18\nauthority: test\n---\n",
            encoding="utf-8",
        )


def valid_agents() -> str:
    return "\n".join(
        [
            "# Test ERP Agent Workspace Index",
            "测试用例生成 docs/TRAE_TEST_WORKFLOW.md",
            "自动化测试执行 docs/AUTO_TEST_WORKFLOW.md",
            "知识库检索 docs/KNOWLEDGE_BASE_RETRIEVER.md",
            "知识库更新 docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md",
            "文件与产物管理 docs/PROJECT_ARTIFACT_PLACEMENT.md",
            "代码审核 docs/AGENT_RULES.md",
            "文档维护 tools/doc_consistency_checker.py",
            "[流程](docs/TRAE_TEST_WORKFLOW.md)",
        ]
    )


def test_checker_accepts_closed_route_graph(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "docs" / "KNOWLEDGE_BASE_RETRIEVER.md").write_text(
        "---\ntitle: KB\npurpose: test\nversion: 1.0.0\nupdated: 2026-08-18\nauthority: test\n---\n# KB\n",
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "doc_consistency_checker.py").write_text("# tool\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")

    result = DocConsistencyChecker(tmp_path).run()

    assert result["passed"] is True
    assert result["exit_code"] == 0


def test_checker_rejects_missing_route_target(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")

    result = DocConsistencyChecker(tmp_path).run()

    assert result["exit_code"] == 2
    assert any(issue["type"] == "missing_route_target" for issue in result["issues"])


def test_checker_rejects_removed_tool_reference(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")
    (tmp_path / "docs" / "PROJECT_ARTIFACT_PLACEMENT.md").write_text(
        "---\ntitle: test\n---\n tools/clean_workspace.py\n", encoding="utf-8"
    )

    result = DocConsistencyChecker(tmp_path).run()

    assert result["exit_code"] == 2
    assert any(issue["type"] == "removed_tool_reference" for issue in result["issues"])


def test_checker_rejects_missing_frontmatter(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")
    (tmp_path / "docs" / "AGENT_RULES.md").write_text("# rules\n", encoding="utf-8")

    result = DocConsistencyChecker(tmp_path).run()

    assert result["exit_code"] == 2
    assert any(issue["type"] == "missing_frontmatter" for issue in result["issues"])


def test_checker_rejects_incomplete_frontmatter(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")
    (tmp_path / "docs" / "AGENT_RULES.md").write_text(
        "---\ntitle: rules\n---\n", encoding="utf-8"
    )

    result = DocConsistencyChecker(tmp_path).run()

    assert result["exit_code"] == 2
    assert any(issue["type"] == "incomplete_frontmatter" for issue in result["issues"])


def test_checker_rejects_frontmatter_body_version_mismatch(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")
    (tmp_path / "docs" / "AGENT_RULES.md").write_text(
        "---\ntitle: rules\npurpose: test\nversion: 3.1.0\nupdated: 2026-08-18\nauthority: test\n---\n> 版本：v3.0\n",
        encoding="utf-8",
    )

    result = DocConsistencyChecker(tmp_path).run()

    assert result["exit_code"] == 2
    assert any(issue["type"] == "version_mismatch" for issue in result["issues"])


def test_checker_ignores_external_version_references_in_document_body(tmp_path):
    write_core_docs(tmp_path)
    (tmp_path / "AGENTS.md").write_text(valid_agents(), encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "doc_consistency_checker.py").write_text("# tool\n", encoding="utf-8")
    (tmp_path / "docs" / "AGENT_RULES.md").write_text(
        "---\ntitle: rules\npurpose: test\nversion: 3.1.0\nupdated: 2026-08-18\nauthority: test\n---\n"
        "# Rules\n\n知识库 API 版本：3.0.0\n",
        encoding="utf-8",
    )

    result = DocConsistencyChecker(tmp_path).run()

    assert result["passed"] is True
