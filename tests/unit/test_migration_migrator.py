import json
from types import SimpleNamespace

import pytest

from modules.trae_test.core.migration import init_db, migrator
from modules.trae_test.core.migration.schema import (
    KBBusinessRule,
    KBChunk,
    KBFile,
    KBProblem,
    KBRequirement,
    KBTestCase,
)

pytestmark = pytest.mark.unit


class FakeQuery:
    def __init__(self, *, first_value=None, all_value=None, count_value=0):
        self.first_value = first_value
        self.all_value = all_value or []
        self.count_value = count_value
        self.deleted = False

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.first_value

    def all(self):
        return self.all_value

    def count(self):
        return self.count_value

    def delete(self):
        self.deleted = True
        return 1


class FakeSession:
    def __init__(self, query_map=None, *, fail_on_add=False):
        self.query_map = query_map or {}
        self.fail_on_add = fail_on_add
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.flushed = False

    def query(self, model):
        return self.query_map.get(model, FakeQuery())

    def add(self, obj):
        if self.fail_on_add:
            raise RuntimeError("add failed")
        if isinstance(obj, KBFile) and getattr(obj, "id", None) is None:
            obj.id = "file-1"
        self.added.append(obj)

    def flush(self):
        self.flushed = True
        for obj in self.added:
            if isinstance(obj, KBFile) and getattr(obj, "id", None) is None:
                obj.id = "file-1"

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _point_migrator_at_tmp(monkeypatch, tmp_path, registry=None):
    original = tmp_path / "original"
    original.mkdir()
    registry_path = tmp_path / "file_registry.json"
    if registry is not None:
        _write_json(registry_path, registry)

    monkeypatch.setattr(migrator, "ORIGINAL_DIR", str(original))
    monkeypatch.setattr(migrator, "REGISTRY_PATH", str(registry_path))
    return original, registry_path


def test_helpers_compute_hash_load_registry_read_content_and_extract_items(tmp_path, monkeypatch):
    original, registry_path = _point_migrator_at_tmp(
        monkeypatch,
        tmp_path,
        {"files": {"sales_rules": {"tags": ["sales"], "classification": "sales"}}},
    )
    source = original / "sales_rules.json"
    _write_json(source, {"requirements": ["one"], "rules": [{"name": "rule"}]})
    invalid = original / "bad.json"
    invalid.write_text("{bad", encoding="utf-8")
    empty = original / "empty.json"
    empty.write_text("  ", encoding="utf-8")

    assert migrator._compute_sha256(str(source))
    assert migrator._load_registry()["files"]["sales_rules"]["tags"] == ["sales"]
    registry_path.unlink()
    assert migrator._load_registry() == {"files": {}}
    assert migrator._read_file_content(str(source))["requirements"] == ["one"]
    assert migrator._read_file_content(str(invalid)) is None
    assert migrator._read_file_content(str(empty)) == {}
    assert migrator._extract_items({"rules": [{"name": "rule"}]}, ["business_rules"]) == [{"name": "rule"}]
    assert migrator._normalize_item("plain") == {"value": "plain"}
    assert migrator._normalize_item(42) == {"value": "42"}


def test_migrate_file_rejects_missing_and_non_json(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)
    (original / "notes.txt").write_text("hello", encoding="utf-8")

    missing = migrator.migrate_file("missing.json")
    non_json = migrator.migrate_file("notes.txt")

    assert missing["success"] is False
    assert "不存在" in missing["error"]
    assert non_json["success"] is False
    assert "JSON" in non_json["error"]


def test_migrate_file_skips_when_hash_already_exists(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)
    _write_json(original / "known.json", {"requirements": []})
    existing_file = SimpleNamespace(id="existing")
    session = FakeSession({KBFile: FakeQuery(first_value=existing_file)})
    monkeypatch.setattr(migrator, "get_session", lambda: session)

    result = migrator.migrate_file("known.json")

    assert result["success"] is True
    assert result["phases"]["skipped"]
    assert session.added == []
    assert session.closed is True


def test_migrate_file_creates_file_and_domain_records(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(
        monkeypatch,
        tmp_path,
        {"files": {"sales_doc": {"tags": ["kb", "sales"], "classification": "sales"}}},
    )
    _write_json(
        original / "sales_doc.json",
        {
            "requirements": [{"id": "REQ-1", "title": "Need approval", "module": "orders"}],
            "business_rules": [{"name": "Approval", "content": "Manager approves"}],
            "problems": [{"title": "Timeout", "severity": "high"}],
            "test_cases": [{"title": "Approve order", "steps": "submit"}],
        },
    )
    session = FakeSession({KBFile: FakeQuery(first_value=None)})
    monkeypatch.setattr(migrator, "get_session", lambda: session)

    result = migrator.migrate_file("sales_doc.json")

    assert result["success"] is True
    assert result["phases"] == {
        "file": "ok",
        "requirements": 1,
        "business_rules": 1,
        "problems": 1,
        "test_cases": 1,
    }
    assert session.committed is True
    assert session.closed is True
    assert [type(obj) for obj in session.added] == [KBFile, KBRequirement, KBBusinessRule, KBProblem, KBTestCase]
    kb_file = session.added[0]
    assert kb_file.tags == ["kb", "sales"]
    assert kb_file.classification == "sales"


def test_migrate_file_rolls_back_invalid_json_and_add_exception(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)
    (original / "invalid.json").write_text("{bad", encoding="utf-8")
    invalid_session = FakeSession({KBFile: FakeQuery(first_value=None)})
    monkeypatch.setattr(migrator, "get_session", lambda: invalid_session)

    invalid_result = migrator.migrate_file("invalid.json")

    assert invalid_result["success"] is False
    assert "JSON" in invalid_result["error"]
    assert invalid_session.rolled_back is True
    assert invalid_session.closed is True

    _write_json(original / "raises.json", {"requirements": []})
    failing_session = FakeSession({KBFile: FakeQuery(first_value=None)}, fail_on_add=True)
    monkeypatch.setattr(migrator, "get_session", lambda: failing_session)

    failing_result = migrator.migrate_file("raises.json")

    assert failing_result["success"] is False
    assert failing_result["error"] == "add failed"
    assert failing_session.rolled_back is True
    assert failing_session.closed is True


def test_migrate_chunks_handles_missing_file_unmigrated_small_and_large_content(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)

    missing = migrator.migrate_chunks("missing.json")
    assert missing["success"] is False
    assert "不存在" in missing["error"]

    _write_json(original / "small.json", {"a": "b"})
    unmigrated_session = FakeSession({KBFile: FakeQuery(first_value=None)})
    monkeypatch.setattr(migrator, "get_session", lambda: unmigrated_session)
    unmigrated = migrator.migrate_chunks("small.json")
    assert unmigrated["success"] is False
    assert "尚未迁移" in unmigrated["error"]

    kb_file = SimpleNamespace(id="file-1", chunk_count=0)
    chunk_query = FakeQuery()
    small_session = FakeSession({KBFile: FakeQuery(first_value=kb_file), KBChunk: chunk_query})
    monkeypatch.setattr(migrator, "get_session", lambda: small_session)
    small = migrator.migrate_chunks("small.json")
    assert small["success"] is True
    assert small["chunk_count"] == 1
    assert kb_file.chunk_count == 1
    assert chunk_query.deleted is True
    assert any(isinstance(obj, KBChunk) and obj.content == {"a": "b"} for obj in small_session.added)

    _write_json(original / "large.json", {"first": "x" * 41000, "second": "y" * 41000})
    large_file = SimpleNamespace(id="file-2", chunk_count=0)
    large_session = FakeSession({KBFile: FakeQuery(first_value=large_file), KBChunk: FakeQuery()})
    monkeypatch.setattr(migrator, "get_session", lambda: large_session)
    large = migrator.migrate_chunks("large.json")
    assert large["success"] is True
    assert large["chunk_count"] == 2
    assert large_file.chunk_count == 2


def test_migrate_chunks_rolls_back_on_exception(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)
    _write_json(original / "boom.json", {"a": "b"})
    failing_session = FakeSession({KBFile: FakeQuery(first_value=SimpleNamespace(id="file-1"))}, fail_on_add=True)
    monkeypatch.setattr(migrator, "get_session", lambda: failing_session)

    result = migrator.migrate_chunks("boom.json")

    assert result["success"] is False
    assert result["error"] == "add failed"
    assert failing_session.rolled_back is True
    assert failing_session.closed is True


def test_migrate_all_discovers_json_files_and_summarizes_success_skip_failure(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)
    for name in ["b.JSON", "a.json", "notes.txt"]:
        (original / name).write_text("{}", encoding="utf-8")
    calls = []

    def fake_migrate_file(name):
        calls.append(("file", name))
        if name == "a.json":
            return {"file": name, "success": True, "phases": {}}
        return {"file": name, "success": True, "phases": {"skipped": "same hash"}}

    def fake_migrate_chunks(name):
        calls.append(("chunks", name))
        return {"success": True, "chunk_count": 1}

    monkeypatch.setattr(migrator, "migrate_file", fake_migrate_file)
    monkeypatch.setattr(migrator, "migrate_chunks", fake_migrate_chunks)

    result = migrator.migrate_all()

    assert result["success"] is True
    assert result["total"] == 2
    assert result["migrated"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert calls == [("file", "a.json"), ("chunks", "a.json"), ("file", "b.JSON"), ("chunks", "b.JSON")]
    assert result["details"][0]["phases"]["chunks"] == {"success": True, "chunk_count": 1}


def test_migrate_all_handles_missing_dir_and_failed_file(tmp_path, monkeypatch):
    missing_dir = tmp_path / "missing"
    monkeypatch.setattr(migrator, "ORIGINAL_DIR", str(missing_dir))
    missing = migrator.migrate_all()
    assert missing["success"] is False
    assert "不存在" in missing["error"]

    original = tmp_path / "original"
    original.mkdir()
    (original / "bad.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(migrator, "ORIGINAL_DIR", str(original))
    monkeypatch.setattr(
        migrator,
        "migrate_file",
        lambda name: {"file": name, "success": False, "phases": {}, "error": "bad"},
    )

    failed = migrator.migrate_all()

    assert failed["success"] is False
    assert failed["failed"] == 1
    assert failed["details"][0]["error"] == "bad"


def test_verify_all_reports_matches_mismatches_counts_and_missing_dir(tmp_path, monkeypatch):
    original, _registry_path = _point_migrator_at_tmp(monkeypatch, tmp_path)
    _write_json(original / "matched.json", {"a": 1})
    _write_json(original / "missing_in_db.json", {"b": 2})
    matched_hash = migrator._compute_sha256(str(original / "matched.json"))
    session = FakeSession(
        {
            KBFile: FakeQuery(
                first_value=None,
                all_value=[SimpleNamespace(original_hash=matched_hash, title="matched")],
                count_value=3,
            ),
            KBRequirement: FakeQuery(count_value=4),
            KBBusinessRule: FakeQuery(count_value=5),
            KBProblem: FakeQuery(count_value=6),
            KBTestCase: FakeQuery(count_value=7),
        }
    )
    monkeypatch.setattr(migrator, "get_session", lambda: session)

    result = migrator.verify_all()

    assert result["success"] is False
    assert result["total"] == 2
    assert result["matched"] == 1
    assert result["mismatched"] == 1
    assert result["db_records"] == {
        "kb_files": 3,
        "kb_requirements": 4,
        "kb_business_rules": 5,
        "kb_problems": 6,
        "kb_test_cases": 7,
    }
    assert session.closed is True

    monkeypatch.setattr(migrator, "ORIGINAL_DIR", str(tmp_path / "not-there"))
    missing = migrator.verify_all()
    assert missing["success"] is False
    assert missing["error"] == "原始目录不存在"


def test_create_all_tables_uses_engine_with_checkfirst(monkeypatch):
    engine = object()
    create_all_calls = []
    monkeypatch.setattr(init_db, "get_engine", lambda: engine)
    monkeypatch.setattr(
        init_db.Base.metadata, "create_all", lambda *args, **kwargs: create_all_calls.append((args, kwargs))
    )

    init_db.create_all_tables()

    assert create_all_calls == [((engine,), {"checkfirst": True})]
