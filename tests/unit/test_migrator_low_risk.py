import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.trae_test.core.migration import migrator
from modules.trae_test.core.migration.schema import KBChunk, KBFile


pytestmark = pytest.mark.unit


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.model is KBFile:
            return self.session.existing_file
        return None

    def all(self):
        if self.model is KBFile:
            return list(self.session.files)
        return []

    def count(self):
        return len(self.all())

    def delete(self):
        self.session.deleted_chunks = True
        return 1


class FakeSession:
    def __init__(self, existing_file=None, fail_commit=False):
        self.existing_file = existing_file
        self.fail_commit = fail_commit
        self.added = []
        self.files = [existing_file] if existing_file is not None else []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.deleted_chunks = False

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, item):
        self.added.append(item)
        if isinstance(item, KBFile) and item not in self.files:
            self.files.append(item)
            self.existing_file = item

    def flush(self):
        for idx, item in enumerate(self.added, start=1):
            if isinstance(item, KBFile):
                item.id = idx

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _patch_dirs(monkeypatch, tmp_path):
    original = tmp_path / "original"
    chunks = tmp_path / "chunks"
    metadata = tmp_path / "metadata"
    original.mkdir()
    chunks.mkdir()
    metadata.mkdir()
    registry = metadata / "file_registry.json"
    registry.write_text(
        json.dumps(
            {
                "files": {
                    "sample": {
                        "tags": ["tag"],
                        "classification": "class-a",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(migrator, "ORIGINAL_DIR", str(original))
    monkeypatch.setattr(migrator, "CHUNKS_DIR", str(chunks))
    monkeypatch.setattr(migrator, "REGISTRY_PATH", str(registry))
    return original, chunks, registry


def test_helpers_read_hash_registry_extract_and_normalize(tmp_path, monkeypatch):
    original, _, registry = _patch_dirs(monkeypatch, tmp_path)
    file_path = original / "sample.json"
    file_path.write_text(json.dumps({"requirements": ["one"], "empty": []}), encoding="utf-8")
    invalid = original / "bad.json"
    invalid.write_text("{bad", encoding="utf-8")
    empty = original / "empty.json"
    empty.write_text("  ", encoding="utf-8")

    assert len(migrator._compute_sha256(str(file_path))) == 64
    assert migrator._load_registry()["files"]["sample"]["classification"] == "class-a"
    assert migrator._read_file_content(str(file_path))["requirements"] == ["one"]
    assert migrator._read_file_content(str(invalid)) is None
    assert migrator._read_file_content(str(empty)) == {}
    assert migrator._extract_items({"requirements": [{"id": "R"}]}, ["requirements"]) == [{"id": "R"}]
    assert migrator._extract_items({"requirement_list": ["R"]}, ["requirement_list"]) == ["R"]
    assert migrator._extract_items({"none": []}, ["requirements"]) == []
    assert migrator._normalize_item("x") == {"value": "x"}
    assert migrator._normalize_item({"x": 1}) == {"x": 1}
    assert migrator._normalize_item(3) == {"value": "3"}
    registry.unlink()
    assert migrator._load_registry() == {"files": {}}


def test_migrate_file_success_skip_invalid_and_error_paths(tmp_path, monkeypatch):
    original, _, _ = _patch_dirs(monkeypatch, tmp_path)
    sample = original / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "requirements": [{"id": "R1", "title": "Req"}],
                "business_rules": [{"name": "Rule", "rule": "must"}],
                "problems": ["problem"],
                "test_cases": [{"title": "Case", "steps": "step"}],
            }
        ),
        encoding="utf-8",
    )
    session = FakeSession()
    monkeypatch.setattr(migrator, "get_session", lambda: session)

    result = migrator.migrate_file("sample.json")

    assert result["success"] is True
    assert result["phases"]["requirements"] == 1
    assert result["phases"]["business_rules"] == 1
    assert result["phases"]["problems"] == 1
    assert result["phases"]["test_cases"] == 1
    assert session.committed is True

    existing = SimpleNamespace(original_hash=migrator._compute_sha256(str(sample)), title="sample", id=1)
    monkeypatch.setattr(migrator, "get_session", lambda: FakeSession(existing_file=existing))
    skipped = migrator.migrate_file("sample.json")
    assert skipped["success"] is True
    assert "skipped" in skipped["phases"]

    bad = original / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(migrator, "get_session", lambda: FakeSession())
    assert migrator.migrate_file("bad.json")["success"] is False
    assert migrator.migrate_file("missing.json")["success"] is False
    assert migrator.migrate_file("sample.md")["success"] is False


def test_migrate_chunks_small_large_missing_and_failure_paths(tmp_path, monkeypatch):
    original, _, _ = _patch_dirs(monkeypatch, tmp_path)
    small = original / "sample.json"
    small.write_text(json.dumps({"a": 1}), encoding="utf-8")
    kb_file = KBFile(title="sample", file_id="sample", original_hash=migrator._compute_sha256(str(small)), chunk_count=0)
    kb_file.id = 7
    session = FakeSession(existing_file=kb_file)
    monkeypatch.setattr(migrator, "get_session", lambda: session)

    result = migrator.migrate_chunks("sample.json")

    assert result["success"] is True
    assert result["chunk_count"] == 1
    assert any(isinstance(item, KBChunk) for item in session.added)
    assert session.deleted_chunks is True

    large = original / "large.json"
    large.write_text(json.dumps({f"k{i}": "x" * 10_000 for i in range(6)}), encoding="utf-8")
    large_file = KBFile(title="large", file_id="large", original_hash=migrator._compute_sha256(str(large)), chunk_count=0)
    large_file.id = 8
    monkeypatch.setattr(migrator, "get_session", lambda: FakeSession(existing_file=large_file))
    assert migrator.migrate_chunks("large.json")["chunk_count"] >= 2

    monkeypatch.setattr(migrator, "get_session", lambda: FakeSession(existing_file=None))
    assert migrator.migrate_chunks("sample.json")["success"] is False
    assert migrator.migrate_chunks("missing.json")["success"] is False


def test_migrate_all_and_verify_all(tmp_path, monkeypatch):
    original, _, _ = _patch_dirs(monkeypatch, tmp_path)
    (original / "sample.json").write_text(json.dumps({"requirements": ["R"]}), encoding="utf-8")
    (original / "second.json").write_text(json.dumps({"rules": ["Rule"]}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(migrator, "migrate_file", lambda fname: calls.append(("file", fname)) or {"success": True, "phases": {}})
    monkeypatch.setattr(migrator, "migrate_chunks", lambda fname: calls.append(("chunks", fname)) or {"success": True})

    result = migrator.migrate_all()

    assert result["success"] is True
    assert result["total"] == 2
    assert result["migrated"] == 2
    assert ("chunks", "sample.json") in calls

    file_hash = migrator._compute_sha256(str(original / "sample.json"))
    session = FakeSession()
    session.files = [SimpleNamespace(original_hash=file_hash, title="sample")]
    monkeypatch.setattr(migrator, "get_session", lambda: session)
    verify = migrator.verify_all()
    assert verify["total"] == 2
    assert verify["matched"] == 1
    assert verify["mismatched"] == 1

    monkeypatch.setattr(migrator, "ORIGINAL_DIR", str(tmp_path / "missing"))
    assert migrator.migrate_all()["success"] is False
    assert migrator.verify_all()["success"] is False
