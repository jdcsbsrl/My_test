import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_MD = PROJECT_ROOT / "AGENTS.md"
DOCUMENTED_LOCAL_STORAGE_PREFIXES = ("assets/knowledge_base/",)


def _read_agents_md() -> str:
    return AGENTS_MD.read_text(encoding="utf-8")


def _slugify_heading(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text).strip()
    text = re.sub(r"\s+", "-", text)
    return text.lower()


def test_agents_md_exists_and_uses_utf8():
    content = _read_agents_md()

    assert content.startswith("# Test ERP Agent Workspace Index")
    assert "HarnessEngineer" in content


def test_agents_md_relative_links_exist_and_heading_anchors_resolve():
    content = _read_agents_md()
    headings = {
        _slugify_heading(line)
        for line in content.splitlines()
        if line.startswith("#")
    }
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)

    assert links, "AGENTS.md should contain index links"

    missing_paths = []
    missing_anchors = []
    for link in links:
        if link.startswith("#"):
            anchor = link[1:].lower()
            if anchor not in headings:
                missing_anchors.append(link)
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):
            continue
        if link.startswith(DOCUMENTED_LOCAL_STORAGE_PREFIXES):
            continue
        if not (PROJECT_ROOT / link).exists():
            missing_paths.append(link)

    assert missing_paths == []
    assert missing_anchors == []


def test_agents_md_markdown_blocks_and_tables_are_structurally_valid():
    lines = _read_agents_md().splitlines()

    code_fence_count = sum(1 for line in lines if line.startswith("```"))
    assert code_fence_count % 2 == 0

    invalid_table_rows = [
        (index, line)
        for index, line in enumerate(lines, start=1)
        if line.startswith("|") and line.count("|") < 3
    ]
    assert invalid_table_rows == []


def test_agents_md_rejects_known_stale_or_private_knowledge_base_indexes():
    content = _read_agents_md()

    forbidden_fragments = [
        "modules/trae_test/utils/index_builder.py",
        "34个原始JSON+MD",
        "82个分块文件",
        "通过 _load_registry() 读取",
        "**版本**: 3.2.0",
        "**更新时间**:",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in content


def test_agents_md_keeps_required_harness_engineer_contract_entries():
    content = _read_agents_md()

    required_fragments = [
        "KnowledgeRetriever",
        "AuditAgent",
        "modules/trae_test/utils/index_builder_v3.py",
        "docs/AUTO_TEST_WORKFLOW.md",
        "tools/run_regression.py",
        "TestReportGenerator",
        "知识库 API 版本",
        "必须通过 `KnowledgeRetriever` API",
        "禁止直接按文件路径读取原始JSON",
        "自动化测试仅允许在 UAT/内网测试环境执行",
        "需用户明确批准",
    ]

    for fragment in required_fragments:
        assert fragment in content


def test_agents_md_keeps_knowledge_base_counts_dynamic():
    content = _read_agents_md()

    assert "数量以 registry/API 为准" in content
    assert "关键词数量以索引元数据为准" in content
    assert "r.get_index()" in content
    assert "r.list_available_files()" in content
