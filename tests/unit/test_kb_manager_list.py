from types import SimpleNamespace

from tools import kb_manager
from tools.kb_manager import KnowledgeBaseManager


def _governance_manager(documents):
    """Build an API-only KB manager fixture; no knowledge source is written."""

    titles = {file_id: document["title"] for file_id, document in documents.items()}

    class FakeRetriever:
        def get_index(self):
            return {
                "files": [{"file_id": file_id, "title": title} for file_id, title in titles.items()],
                "index_status": {"valid": True, "missing_files": [], "stale_files": []},
            }

        def list_available_files(self):
            return list(reversed(list(documents)))

        def load_aggregated_data(self, title):
            return next(document for document in documents.values() if document["title"] == title)

    manager = object.__new__(KnowledgeBaseManager)
    manager.retriever = FakeRetriever()
    manager.scan_all = lambda: {
        "total_files": len(documents),
        "needs_processing": [],
        "already_processed": [],
        "errors": [],
    }
    return manager


def test_dedupe_report_is_read_only_and_reports_deterministic_exact_findings():
    manager = _governance_manager(
        {
            "a": {"title": "WMS 规则", "business_rules": [{"rule_id": "RULE_SHARED", "content": "盘点 原因 必须展示"}]},
            "b": {
                "title": "wms　规则",
                "business_rules": [{"rule_id": "RULE_SHARED", "content": "盘点 原因 必须展示"}],
            },
            "c": {"title": "独立规则", "business_rules": [{"rule_id": "RULE_OTHER", "content": "不同内容"}]},
        }
    )

    result = manager.dedupe_report()

    assert result["success"] is True
    assert result["read_only"] is True
    assert result["summary"]["registered_file_count"] == 3
    assert result["summary"]["structured_rule_count"] == 3
    assert result["normalized_title_duplicates"][0]["key"] == "wms 规则"
    assert [item["file_id"] for item in result["cross_file_rule_id_duplicates"][0]["entries"]] == ["a", "b"]
    assert len(result["exact_content_duplicates"]) == 1
    assert "content" not in result["exact_content_duplicates"][0]["entries"][0]
    assert result["similarity_candidates"] == []


def test_health_check_reports_registry_index_mismatch_without_mutation():
    manager = _governance_manager({"rules": {"title": "规则", "business_rules": []}})
    manager.retriever.get_index = lambda: {
        "files": [{"file_id": "rules", "title": "规则"}],
        "index_status": {"valid": False, "missing_files": ["rules"], "stale_files": []},
    }

    result = manager.health_check()

    assert result["success"] is False
    assert result["read_only"] is True
    assert result["registered_file_count"] == 1
    assert result["errors"] == [{"component": "global_index", "error": "registry/index mismatch"}]


def test_list_files_recursively_includes_json_and_gzip_indexes(tmp_path):
    original_dir = tmp_path / "original"
    content_dir = tmp_path / "chunks"
    index_dir = tmp_path / "index"
    original_dir.mkdir()
    content_dir.mkdir()
    (index_dir / "files").mkdir(parents=True)
    (index_dir / "global").mkdir()
    (index_dir / "inverted").mkdir()

    (original_dir / "rule.json").write_bytes(b"1234")
    (content_dir / "rule_chunk_000.json").write_bytes(b"123456")
    (index_dir / "files" / "rule_index.json").write_bytes(b"12345678")
    (index_dir / "global" / "global_index.json").write_bytes(b"1234567890")
    (index_dir / "inverted" / "keywords.json.gz").write_bytes(b"123456789012")
    (index_dir / "inverted" / ".keep").write_bytes(b"ignored")

    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(
        ORIGINAL_DIR=str(original_dir),
        CONTENT_DIR=str(content_dir),
        INDEX_DIR=str(index_dir),
    )

    result = manager.list_files()

    assert [item["filename"] for item in result["index"]] == [
        "files/rule_index.json",
        "global/global_index.json",
        "inverted/keywords.json.gz",
    ]
    assert result["summary"] == {
        "original_count": 1,
        "content_count": 1,
        "index_count": 3,
        "original_size_kb": 0.0,
        "content_size_kb": 0.01,
        "index_size_kb": 0.03,
        "total_size_kb": 0.04,
    }


def test_process_file_synchronizes_secondary_indexes_and_propagates_failure():
    calls = []

    class FakeIndexBuilder:
        def build_global_index(self):
            calls.append("global")
            return {"success": True}

        def build_inverted_index(self):
            calls.append("inverted")
            return {"success": True}

    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(process_file_complete=lambda path: {"success": True, "file_path": path})
    manager.index_builder = FakeIndexBuilder()
    manager.retriever = SimpleNamespace(refresh_registry=lambda: calls.append("refresh"))

    result = manager.process_file("rule.json")

    assert result["success"] is True
    assert result["secondary_indexes"]["success"] is True
    assert result["retriever_refresh"]["success"] is True
    assert calls == ["global", "inverted", "refresh"]

    manager.index_builder = SimpleNamespace(
        build_global_index=lambda: {"success": False, "error": "global failed"},
    )
    failed = manager.process_file("rule.json")
    assert failed["success"] is False
    assert failed["error"] == "global failed"


def test_process_file_propagates_retriever_refresh_failure():
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(process_file_complete=lambda path: {"success": True, "file_path": path})
    manager.index_builder = SimpleNamespace(
        build_global_index=lambda: {"success": True},
        build_inverted_index=lambda: {"success": True},
    )

    def fail_refresh():
        raise RuntimeError("refresh failed")

    manager.retriever = SimpleNamespace(refresh_registry=fail_refresh)

    result = manager.process_file("rule.json")

    assert result["success"] is False
    assert result["retriever_refresh"] == {"success": False, "error": "refresh failed"}
    assert result["error"] == "refresh failed"


def test_migrate_registers_before_processing_and_rebuilds_after_rollback(tmp_path, monkeypatch):
    calls = []

    class FakeMetadataManager:
        def scan_and_register_all(self):
            calls.append("registry")
            return {"success": True}

    source = tmp_path / "source.json"
    source.write_text(
        '{"business_rules":[{"rule_id":"RULE_1","keywords":["rule"],"content":"rule content"}]}',
        encoding="utf-8",
    )
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir))
    manager.process_file = lambda path: calls.append("process") or {"success": False, "error": "process failed"}
    manager._sync_secondary_indexes = lambda: calls.append("secondary") or {"success": True}
    manager._audit_verification_result = lambda result: True
    monkeypatch.setattr(kb_manager, "MetadataManager", FakeMetadataManager)

    result = manager.migrate_file(str(source), "target")

    assert result["success"] is False
    assert not (original_dir / "target.json").exists()
    assert calls == ["registry", "process", "registry", "secondary"]


def test_structured_rule_contract_is_strict_only_when_requested():
    incomplete = {"business_rules": [{"rule_id": "RULE_1", "keywords": []}]}

    permissive = KnowledgeBaseManager.validate_rule_contract(incomplete)
    strict = KnowledgeBaseManager.validate_rule_contract(incomplete, strict=True)

    assert permissive["success"] is True
    assert permissive["warnings"]
    assert strict["success"] is False
    assert any("keywords" in error for error in strict["errors"])
    assert any("content" in error for error in strict["errors"])


def test_structured_rule_contract_rejects_duplicate_ids_and_accepts_valid_rules():
    valid = {
        "business_rules": [
            {"rule_id": "RULE_1", "keywords": ["primary", "alias"], "content": "first rule"},
            {"rule_id": "RULE_2", "keywords": ["secondary"], "content": "second rule"},
        ]
    }

    result = KnowledgeBaseManager.validate_rule_contract(valid, strict=True)
    assert result == {"success": True, "strict": True, "checked_rules": 2, "errors": [], "warnings": []}

    valid["business_rules"][1]["rule_id"] = "RULE_1"
    duplicate = KnowledgeBaseManager.validate_rule_contract(valid, strict=True)
    assert duplicate["success"] is False
    assert duplicate["errors"] == ["duplicate rule_id: RULE_1"]


def test_lifecycle_rule_contract_validates_status_and_supersedes_relationships():
    valid = {
        "business_rules": [
            {"rule_id": "RULE_ACTIVE", "keywords": ["active"], "content": "active", "status": "active"},
            {
                "rule_id": "RULE_SUPERSEDED",
                "keywords": ["old"],
                "content": "old",
                "status": "superseded",
                "supersedes": ["RULE_ACTIVE"],
            },
            {"rule_id": "RULE_DRAFT", "keywords": ["draft"], "content": "draft", "status": "draft"},
        ]
    }

    assert KnowledgeBaseManager.validate_rule_contract(valid, strict=True)["success"] is True

    invalid_status = {
        "business_rules": [{"rule_id": "RULE_1", "keywords": ["rule"], "content": "rule", "status": "published"}]
    }
    invalid_status_result = KnowledgeBaseManager.validate_rule_contract(invalid_status, strict=True)
    assert invalid_status_result["success"] is False
    assert any("status must be one of" in item for item in invalid_status_result["errors"])

    missing_target = {
        "business_rules": [
            {
                "rule_id": "RULE_1",
                "keywords": ["rule"],
                "content": "rule",
                "status": "superseded",
            }
        ]
    }
    missing_result = KnowledgeBaseManager.validate_rule_contract(missing_target, strict=True)
    assert missing_result["success"] is False
    assert any("supersedes is required" in item for item in missing_result["errors"])

    self_reference = {
        "business_rules": [
            {
                "rule_id": "RULE_1",
                "keywords": ["rule"],
                "content": "rule",
                "status": "superseded",
                "supersedes": ["RULE_1"],
            }
        ]
    }
    self_result = KnowledgeBaseManager.validate_rule_contract(self_reference, strict=True)
    assert self_result["success"] is False
    assert any("must not reference its own rule_id" in item for item in self_result["errors"])


def test_lifecycle_cross_file_supersedes_is_warning_not_strict_error():
    document = {
        "business_rules": [
            {
                "rule_id": "RULE_NEW",
                "keywords": ["new"],
                "content": "new",
                "status": "superseded",
                "supersedes": ["RULE_IN_OTHER_FILE"],
            }
        ]
    }

    result = KnowledgeBaseManager.validate_rule_contract(document, strict=True)

    assert result["success"] is True
    assert result["lifecycle_warnings"] == [
        "business_rules[0].supersedes target not found in this file; verify cross-file reference: RULE_IN_OTHER_FILE"
    ]


def test_validate_file_supports_repeated_keywords_and_expected_rule_ids(tmp_path, monkeypatch):
    original_dir = tmp_path / "original"
    index_dir = tmp_path / "index" / "files"
    original_dir.mkdir()
    index_dir.mkdir(parents=True)
    document = {
        "business_rules": [
            {"rule_id": "RULE_1", "keywords": ["first"], "content": "first rule"},
            {"rule_id": "RULE_2", "keywords": ["second"], "content": "second rule"},
        ]
    }
    (original_dir / "rules.json").write_text(kb_manager.json.dumps(document), encoding="utf-8")
    (index_dir / "rules_index.json").write_text("{}", encoding="utf-8")

    class FakeMetadataManager:
        def load_registry(self):
            return {"files": {"rules": {"file_id": "rules"}}}

    class FakeRetriever:
        def load_aggregated_data(self, title):
            assert title == "rules"
            return document

        def search_business_rules(self, keyword):
            return (
                [{"file_id": "rules", "rule_id": "RULE_1"}]
                if keyword == "first"
                else [{"file_id": "rules", "rule_id": "RULE_2"}]
            )

    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir), INDEX_DIR=str(tmp_path / "index"))
    manager.retriever = FakeRetriever()
    monkeypatch.setattr(kb_manager, "MetadataManager", FakeMetadataManager)

    result = manager.validate_file(
        "rules",
        ["first", "second"],
        expected_rule_ids=["RULE_1", "RULE_2"],
        strict_rules=True,
    )

    assert result["success"] is True
    assert result["retrieval_hit"] is True
    assert [item["keyword"] for item in result["keyword_results"]] == ["first", "second"]
    assert result["matched_rule_ids"] == ["RULE_1", "RULE_2"]
    assert result["missing_expected_rule_ids"] == []

    missing = manager.validate_file("rules", "first", expected_rule_ids=["RULE_2"], strict_rules=True)
    assert missing["success"] is False
    assert missing["missing_expected_rule_ids"] == ["RULE_2"]


def test_migrate_rejects_invalid_new_structured_rule_before_copy(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"business_rules":[{"rule_id":"RULE_1"}]}', encoding="utf-8")
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir))

    result = manager.migrate_file(str(source), "target")

    assert result["success"] is False
    assert result["error"] == "rule contract validation failed"
    assert not (original_dir / "target.json").exists()
