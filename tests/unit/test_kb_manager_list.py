import json
import os
import sys
from types import SimpleNamespace

import pytest

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


def test_process_file_propagates_vector_failure():
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(process_file_complete=lambda path: {"success": True, "file_path": path})
    manager.index_builder = SimpleNamespace(
        build_global_index=lambda: {"success": True},
        build_inverted_index=lambda: {"success": True},
    )
    manager.retriever = SimpleNamespace(refresh_registry=lambda: None)
    manager.sync_vector_file = lambda path: {"success": False, "error": "vector failed"}

    result = manager.process_file("rule.json", sync_vector=True)

    assert result["success"] is False
    assert result["vector"] == {"success": False, "error": "vector failed"}
    assert result["error"] == "vector failed"


def test_force_split_restores_threshold_when_splitter_raises():
    class FailingSplitter:
        size_threshold = 1024

        @staticmethod
        def split_file(path):
            raise RuntimeError("split failed")

    manager = object.__new__(KnowledgeBaseManager)
    manager.splitter = FailingSplitter()

    with pytest.raises(RuntimeError, match="split failed"):
        manager.split_file("rule.json", force=True)

    assert manager.splitter.size_threshold == 1024


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
    manager.retriever = SimpleNamespace(refresh_registry=lambda: calls.append("refresh"))
    manager._audit_verification_result = lambda result: True
    monkeypatch.setattr(kb_manager, "MetadataManager", FakeMetadataManager)

    result = manager.migrate_file(str(source), "target")

    assert result["success"] is False
    assert result["error"] == "process failed"
    assert not (original_dir / "target.json").exists()
    assert calls == ["registry", "process", "registry", "secondary", "refresh"]
    assert result["rollback"]["retriever_refresh"]["success"] is True


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


@pytest.mark.parametrize("target_title", ["../outside", r"..\outside"])
def test_migrate_rejects_path_traversal_title(tmp_path, target_title):
    source = tmp_path / "source.json"
    source.write_text(
        '{"business_rules":[{"rule_id":"RULE_1","keywords":["rule"],"content":"rule content"}]}',
        encoding="utf-8",
    )
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir))

    result = manager.migrate_file(str(source), target_title)

    assert result["success"] is False
    assert "单层文件名" in result["error"]
    assert not (tmp_path / "outside.json").exists()


def test_migrate_rejects_absolute_title(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        '{"business_rules":[{"rule_id":"RULE_1","keywords":["rule"],"content":"rule content"}]}',
        encoding="utf-8",
    )
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir))

    result = manager.migrate_file(str(source), str(tmp_path / "outside"))

    assert result["success"] is False
    assert "单层文件名" in result["error"]
    assert not (tmp_path / "outside.json").exists()


def test_print_migrate_result_omits_processing_section_when_not_processed(capsys):
    kb_manager.print_migrate_result(
        {
            "success": False,
            "source_path": "source.json",
            "target_path": "",
            "processed": None,
            "error": "migration failed",
        }
    )

    output = capsys.readouterr().out
    assert "处理结果:" not in output
    assert "索引:" not in output
    assert "migration failed" in output


def test_process_command_returns_failure_for_failed_top_level_result(monkeypatch):
    class FakeManager:
        def process_file(self, path, sync_vector=False, strict_rules=False):
            return {"success": False, "error": "rule contract validation failed"}

    monkeypatch.setattr(kb_manager, "KnowledgeBaseManager", FakeManager)
    monkeypatch.setattr(sys, "argv", ["kb_manager.py", "process", "--file", "rule.json"])

    assert kb_manager.main() == 1


def test_lint_treats_contextual_token_as_warning_but_blocks_credentials(tmp_path):
    contextual = tmp_path / "contextual.json"
    contextual.write_text('{"content":"不得把 token 写入日志"}', encoding="utf-8")
    credential = tmp_path / "credential.json"
    credential.write_text(
        '{"authorization":"Bearer abcdefghijklmnop"}',
        encoding="utf-8",
    )
    json_credential = tmp_path / "json_credential.json"
    json_credential.write_text('{"password": "Lkj8*hgT2"}', encoding="utf-8")
    manager = object.__new__(KnowledgeBaseManager)

    contextual_result = manager.lint_file(str(contextual))
    credential_result = manager.lint_file(str(credential))
    json_credential_result = manager.lint_file(str(json_credential))

    assert contextual_result["success"] is True
    assert "token" in contextual_result["warnings"]
    assert credential_result["success"] is False
    assert "bearer_token" in credential_result["blocked_findings"]
    assert "password" not in credential_result["warnings"]
    assert json_credential_result["success"] is False
    assert "password_assignment" in json_credential_result["blocked_findings"]


@pytest.mark.parametrize(
    "content",
    [
        "db_password = Xyz12345",
        "api_secret: Abcd1234",
        '{"db_password": "Xyz12345"}',
    ],
)
def test_lint_blocks_prefixed_credential_keys(tmp_path, content):
    source = tmp_path / "prefixed_credential.json"
    source.write_text(content, encoding="utf-8")
    manager = object.__new__(KnowledgeBaseManager)

    result = manager.lint_file(str(source))

    assert result["success"] is False
    assert "password_assignment" in result["blocked_findings"]


def test_lint_warns_on_password_hash_without_blocking(tmp_path):
    source = tmp_path / "password_hash.json"
    source.write_text('{"password_hash": "Abcd1234"}', encoding="utf-8")
    manager = object.__new__(KnowledgeBaseManager)

    result = manager.lint_file(str(source))

    assert result["success"] is True
    assert "password_assignment" not in result["blocked_findings"]
    assert "password" in result["warnings"]


def test_integrity_hashing_is_shared_with_legacy_verifier(tmp_path):
    from modules.trae_test.utils.file_splitter import compute_content_hash, normalize_for_integrity
    from tools.verify_knowledge_base import KnowledgeBaseVerifier

    content = {
        "created_at": "2026-09-19T00:00:00Z",
        "business_rules": [{"rule_id": "RULE_1", "content": "rule"}],
    }
    source = tmp_path / "rules.json"
    source.write_text('{"created_at":"old","business_rules":[{"content":"rule","rule_id":"RULE_1"}]}', encoding="utf-8")
    verifier = object.__new__(KnowledgeBaseVerifier)

    assert normalize_for_integrity(content) == {"business_rules": [{"rule_id": "RULE_1", "content": "rule"}]}
    assert verifier._compute_content_hash(content) == compute_content_hash(content)
    assert verifier._load_and_normalize(str(source)) == normalize_for_integrity(json.loads(source.read_text()))


def test_verify_integrity_compares_normalized_json_content(tmp_path):
    from modules.trae_test.utils.file_splitter import JSONFileSplitter

    original = tmp_path / "rules.json"
    original.write_text(
        '{\n    "created_at": "2026-09-19T00:00:00Z",\n'
        '    "business_rules": [{"rule_id": "RULE_1", "content": "rule"}]\n}\n',
        encoding="utf-8",
    )
    chunk = tmp_path / "rules_chunk_000.json"
    chunk.write_text(
        '{"chunk_index": 0, "total_chunks": 1, '
        '"data": {"business_rules": [{"rule_id": "RULE_1", "content": "rule"}]}}',
        encoding="utf-8",
    )
    splitter = object.__new__(JSONFileSplitter)

    result = splitter.verify_integrity(str(original), [str(chunk)])

    assert result["success"] is True
    assert result["content_match"] is True
    assert result["hash_match"] is True
    assert result["byte_match"] is False


def test_verify_integrity_cleans_temp_file_when_reconstruction_fails(tmp_path):
    from modules.trae_test.utils.file_splitter import JSONFileSplitter

    original = tmp_path / "rules.json"
    original.write_text('{"business_rules": []}', encoding="utf-8")
    splitter = object.__new__(JSONFileSplitter)
    captured = {}

    def fail_reconstruction(chunk_files, output_path):
        captured["output_path"] = output_path
        return False

    splitter.reconstruct_file = fail_reconstruction

    result = splitter.verify_integrity(str(original), [])

    assert result["success"] is False
    assert result["error"] == "重建文件失败"
    assert not os.path.exists(captured["output_path"])


def test_verify_integrity_reports_missing_original_file(tmp_path):
    from modules.trae_test.utils.file_splitter import JSONFileSplitter

    splitter = object.__new__(JSONFileSplitter)

    result = splitter.verify_integrity(str(tmp_path / "missing.json"), [])

    assert result["success"] is False
    assert result["error"] == "原始文件不存在"


def test_metadata_manager_exposes_shared_file_id_normalization():
    from modules.trae_test.utils.metadata_manager import MetadataManager, normalize_file_id

    assert normalize_file_id("Sales Rules") == "sales_rules"
    assert MetadataManager.normalize_file_id("Sales Rules") == "sales_rules"


def test_process_all_uses_single_file_pipeline_and_propagates_options():
    calls = []

    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(
        ORIGINAL_DIR="/kb/original",
        scan_all_files=lambda: {
            "needs_processing": [{"file": "rules.json"}],
            "already_processed": [{"file": "done.json"}],
            "errors": [],
        },
    )

    def process_file(path, sync_vector=False, strict_rules=False, rebuild_derived=True):
        calls.append((path, sync_vector, strict_rules, rebuild_derived))
        return {"success": True}

    manager.process_file = process_file
    manager._sync_secondary_indexes = lambda: calls.append("secondary") or {"success": True}
    manager._refresh_retriever_state = lambda: calls.append("refresh") or {"success": True}

    result = manager.process_all(sync_vector=True, strict_rules=True)

    assert result["success"] is True
    assert result["processed"] == ["rules.json"]
    assert result["skipped"] == ["done.json"]
    assert calls == [
        (os.path.join("/kb/original", "rules.json"), True, True, False),
        "secondary",
        "refresh",
    ]


def test_process_all_returns_failure_for_scan_or_file_errors():
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(
        ORIGINAL_DIR="/kb/original",
        scan_all_files=lambda: {
            "needs_processing": [{"file": "rules.json"}],
            "already_processed": [],
            "errors": [{"file": "broken.json", "error": "read failed"}],
        },
    )
    manager.process_file = lambda *args, **kwargs: {"success": False, "error": "index failed"}
    manager._sync_secondary_indexes = lambda: {"success": True}
    manager._refresh_retriever_state = lambda: {"success": True}

    result = manager.process_all()

    assert result["success"] is False
    assert result["errors"] == [{"file": "broken.json", "error": "read failed"}]
    assert result["failed"][0]["error"] == "index failed"


def test_audit_disabled_with_blocking_enabled_fails_closed(monkeypatch):
    manager = object.__new__(KnowledgeBaseManager)
    monkeypatch.delenv("KB_AUDIT_ENABLED", raising=False)
    monkeypatch.setenv("KB_AUDIT_BLOCK_ON_FAIL", "1")

    assert manager._audit_verification_result({"file_results": []}) is False


def test_audit_config_conflict_reason_is_reported(monkeypatch, tmp_path):
    original_dir = tmp_path / "original"
    index_dir = tmp_path / "index"
    original_dir.mkdir()
    index_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir), INDEX_DIR=str(index_dir))
    manager.retriever = SimpleNamespace(get_all_chunks=lambda title: [])
    monkeypatch.delenv("KB_AUDIT_ENABLED", raising=False)
    monkeypatch.setenv("KB_AUDIT_BLOCK_ON_FAIL", "1")

    result = manager.verify_file("rules")

    assert result["audit"]["success"] is False
    assert result["audit"]["blocking"] is True
    assert result["audit"]["reason"] == "config_conflict"


def test_audit_config_is_not_conflicting_when_both_features_are_enabled(monkeypatch):
    manager = object.__new__(KnowledgeBaseManager)
    monkeypatch.setenv("KB_AUDIT_ENABLED", "1")
    monkeypatch.setenv("KB_AUDIT_BLOCK_ON_FAIL", "1")

    assert manager._audit_config_conflict() is False


def test_audit_context_and_details_are_forwarded(monkeypatch):
    captured = {}

    class FakeGateway:
        def audit(self, target, audit_type, context):
            captured.update(target=target, audit_type=audit_type, context=context)
            return SimpleNamespace(passed=True, errors=[])

    from modules.trae_test.orchestrator import audit_gateway

    monkeypatch.setenv("KB_AUDIT_ENABLED", "1")
    monkeypatch.setenv("KB_AUDIT_BLOCK_ON_FAIL", "1")
    monkeypatch.setattr(audit_gateway, "AuditGateway", FakeGateway)
    manager = object.__new__(KnowledgeBaseManager)

    assert (
        manager._audit_verification_result(
            {
                "total_files": 1,
                "verified": 1,
                "failed": 0,
                "file_results": [
                    {
                        "file_name": "rules.json",
                        "passed": True,
                        "details": {"chunk_count": 3, "valid_chunk_count": 2, "hash_match": True},
                    }
                ],
            }
        )
        is True
    )

    assert captured["context"]["block_on_fail"] is False
    assert captured["target"]["file_results"][0]["chunk_count"] == 3
    assert captured["target"]["file_results"][0]["valid_chunk_count"] == 2
    assert captured["target"]["file_results"][0]["hash_match"] is True


def test_verify_uses_normalized_index_filename(tmp_path):
    original_dir = tmp_path / "original"
    index_dir = tmp_path / "index" / "files"
    original_dir.mkdir()
    index_dir.mkdir(parents=True)
    (original_dir / "Sales Rules.json").write_text('{"business_rules": []}', encoding="utf-8")
    (index_dir / "sales_rules_index.json").write_text("{}", encoding="utf-8")

    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(
        ORIGINAL_DIR=str(original_dir),
        INDEX_DIR=str(tmp_path / "index"),
        CONTENT_DIR=str(tmp_path / "chunks"),
    )
    manager.retriever = SimpleNamespace(get_all_chunks=lambda title: [])
    manager._audit_verification_result = lambda result: True

    result = manager.verify_file("Sales Rules")

    assert result["index_exists"] is True
    assert result["success"] is True


def test_verify_file_propagates_integrity_result_and_audit_details(tmp_path):
    original_dir = tmp_path / "original"
    index_dir = tmp_path / "index" / "files"
    chunks_dir = tmp_path / "chunks"
    original_dir.mkdir()
    index_dir.mkdir(parents=True)
    chunks_dir.mkdir()
    (original_dir / "rules.json").write_text('{"business_rules": []}', encoding="utf-8")
    (index_dir / "rules_index.json").write_text("{}", encoding="utf-8")
    (chunks_dir / "rules_chunk_000.json").write_text("{}", encoding="utf-8")

    captured = {}
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(
        ORIGINAL_DIR=str(original_dir),
        INDEX_DIR=str(tmp_path / "index"),
        CONTENT_DIR=str(chunks_dir),
    )
    manager.retriever = SimpleNamespace(
        get_all_chunks=lambda title: [
            {
                "chunk_index": 0,
                "total_chunks": 1,
                "data": {},
                "source_filename": "rules_chunk_000.json",
            }
        ]
    )
    manager.splitter = SimpleNamespace(
        verify_integrity=lambda original, chunks: captured.update(original=original, chunks=chunks)
        or {"success": True, "hash_match": True, "byte_match": False}
    )

    def capture_audit(audit_input):
        captured["audit"] = audit_input
        return True

    manager._audit_verification_result = capture_audit

    result = manager.verify_file("rules")

    assert result["success"] is True
    assert result["integrity"]["hash_match"] is True
    assert captured["chunks"] == [str(chunks_dir / "rules_chunk_000.json")]
    details = captured["audit"]["file_results"][0]["details"]
    assert details["chunk_count"] == 1
    assert details["valid_chunk_count"] == 1
    assert details["hash_match"] is True


def test_migrate_marks_rollback_after_processing_failure(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text('{"business_rules": []}', encoding="utf-8")
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir))
    manager.validate_rule_contract_file = lambda path, strict=False: {"success": True}
    manager.process_file = lambda path: {"success": False, "error": "index failed"}
    manager._rollback_migration = lambda *args: {"success": True, "errors": []}
    manager._audit_verification_result = lambda audit_input: True

    class FakeMetadataManager:
        def scan_and_register_all(self):
            return {"success": True}

    monkeypatch.setattr(kb_manager, "MetadataManager", FakeMetadataManager)

    result = manager.migrate_file(str(source), "target")

    assert result["success"] is False
    assert result["error"] == "index failed"
    assert result["rolled_back"] is True
    assert result["rollback"]["success"] is True


def test_validate_uses_normalized_index_filename(tmp_path, monkeypatch):
    original_dir = tmp_path / "original"
    index_dir = tmp_path / "index" / "files"
    original_dir.mkdir()
    index_dir.mkdir(parents=True)
    (original_dir / "Sales Rules.md").write_text("rules", encoding="utf-8")
    (index_dir / "sales_rules_index.json").write_text("{}", encoding="utf-8")

    class FakeMetadataManager:
        def load_registry(self):
            return {"files": {"sales_rules": {"file_id": "sales_rules"}}}

    monkeypatch.setattr(kb_manager, "MetadataManager", FakeMetadataManager)
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(
        ORIGINAL_DIR=str(original_dir),
        INDEX_DIR=str(tmp_path / "index"),
    )
    manager.retriever = SimpleNamespace(load_aggregated_data=lambda title: {"raw_markdown": "rules"})

    result = manager.validate_file("Sales Rules")

    assert result["registered"] is True
    assert result["index_exists"] is True
    assert result["success"] is True


def test_monitor_scan_uses_normalized_index_filename(tmp_path):
    from modules.trae_test.utils.kb_monitor import KnowledgeBaseMonitor

    original_dir = tmp_path / "original"
    index_dir = tmp_path / "index" / "files"
    original_dir.mkdir()
    index_dir.mkdir(parents=True)
    (original_dir / "Sales Rules.md").write_text("rules", encoding="utf-8")
    (index_dir / "sales_rules_index.json").write_text("{}", encoding="utf-8")

    monitor = object.__new__(KnowledgeBaseMonitor)
    monitor.ORIGINAL_DIR = str(original_dir)
    monitor.INDEX_DIR = str(tmp_path / "index")
    monitor.check_file_size = lambda path: {
        "file_size": os.path.getsize(path),
        "error": "",
    }

    result = monitor.scan_all_files()

    assert result["needs_processing"] == []
    assert result["already_processed"][0]["file"] == "Sales Rules.md"


def test_print_results_include_audit_and_rollback(capsys):
    kb_manager.print_verify_result(
        {
            "file_title": "rules",
            "success": True,
            "index_exists": True,
            "chunks_exist": True,
            "original_exists": True,
            "chunks_valid": [],
            "chunk_count": 2,
            "valid_chunk_count": 2,
            "integrity": {"success": True, "hash_match": True, "byte_match": False},
            "audit": {"success": True, "blocking": True},
            "error": "",
        }
    )
    kb_manager.print_migrate_result(
        {
            "success": False,
            "source_path": "source.json",
            "target_path": "target.json",
            "processed": None,
            "rollback": {"success": False, "errors": ["restore failed"]},
            "audit": {"success": False, "blocking": True},
            "error": "migration failed",
        }
    )

    output = capsys.readouterr().out
    assert "审核: [OK]" in output
    assert "完整性: [OK]" in output
    assert "内容哈希匹配: [OK]" in output
    assert "字节哈希匹配: [FAIL]" in output
    assert "有效块数量: 2" in output
    assert "回滚:" in output
    assert "restore failed" in output
    assert "审核: [FAIL]" in output


@pytest.mark.parametrize("target_title", ["CON", "CON .txt", "NUL.txt", "name.", "name ", "LPT1.log"])
def test_migrate_rejects_windows_invalid_titles(tmp_path, target_title):
    source = tmp_path / "source.json"
    source.write_text(
        '{"business_rules":[{"rule_id":"RULE_1","keywords":["rule"],"content":"rule content"}]}',
        encoding="utf-8",
    )
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    manager = object.__new__(KnowledgeBaseManager)
    manager.monitor = SimpleNamespace(ORIGINAL_DIR=str(original_dir))

    result = manager.migrate_file(str(source), target_title)

    assert result["success"] is False
    assert "有效单层文件名" in result["error"]


def test_process_all_cli_passes_strict_and_vector_options(monkeypatch):
    captured = {}

    class FakeManager:
        def process_all(self, sync_vector=False, strict_rules=False):
            captured.update(sync_vector=sync_vector, strict_rules=strict_rules)
            return {"success": True, "processed": [], "failed": [], "skipped": [], "errors": []}

    monkeypatch.setattr(kb_manager, "KnowledgeBaseManager", FakeManager)
    monkeypatch.setattr(
        sys,
        "argv",
        ["kb_manager.py", "process-all", "--sync-vector", "--strict-rules"],
    )

    assert kb_manager.main() == 0
    assert captured == {"sync_vector": True, "strict_rules": True}
