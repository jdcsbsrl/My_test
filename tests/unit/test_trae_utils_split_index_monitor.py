import gzip
import json
import os
from pathlib import Path

import pytest

from modules.trae_test.utils import file_splitter, index_builder_v3, kb_monitor
from modules.trae_test.utils.file_splitter import JSONFileSplitter, split_file_cli
from modules.trae_test.utils.index_builder_v3 import IndexBuilderV3
from modules.trae_test.utils.kb_monitor import FileSizeHook, KnowledgeBaseMonitor


pytestmark = pytest.mark.unit


def _patch_path_manager(monkeypatch, kb_dir: Path):
    data = kb_dir / "data"
    original = data / "original"
    chunks = data / "chunks"
    index = kb_dir / "index"
    metadata = kb_dir / "metadata"

    def ensure():
        for directory in (kb_dir, data, original, chunks, index, metadata):
            directory.mkdir(parents=True, exist_ok=True)

    for module in (file_splitter, index_builder_v3):
        monkeypatch.setattr(module.PathManager, "get_kb_base_dir", classmethod(lambda cls: str(kb_dir)))
        monkeypatch.setattr(module.PathManager, "get_data_dir", classmethod(lambda cls: str(data)))
        monkeypatch.setattr(module.PathManager, "get_original_dir", classmethod(lambda cls: str(original)))
        monkeypatch.setattr(module.PathManager, "get_chunks_dir", classmethod(lambda cls: str(chunks)))
        monkeypatch.setattr(module.PathManager, "get_index_dir", classmethod(lambda cls: str(index)))
        monkeypatch.setattr(module.PathManager, "get_metadata_dir", classmethod(lambda cls: str(metadata)))
        monkeypatch.setattr(module.PathManager, "ensure_kb_directories", classmethod(lambda cls: ensure()))

    ensure()
    return {"kb": kb_dir, "data": data, "original": original, "chunks": chunks, "index": index, "metadata": metadata}


class TestJSONFileSplitter:
    def test_split_file_returns_success_without_chunks_for_small_file(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        source = dirs["original"] / "small.json"
        source.write_text(json.dumps({"a": "b"}), encoding="utf-8")

        result = JSONFileSplitter(size_threshold=10_000).split_file(str(source))

        assert result["success"] is True
        assert result["chunk_count"] == 0
        assert result["original_path"] == str(source)

    def test_split_file_splits_large_list_and_validates_chunks(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        source = tmp_path / "large-list.json"
        source.write_text(json.dumps([{"value": "x" * 40}, {"value": "y" * 40}, {"value": "z" * 40}]), encoding="utf-8")
        splitter = JSONFileSplitter(size_threshold=55)

        result = splitter.split_file(str(source))

        assert result["success"] is True
        assert result["chunk_count"] >= 2
        assert Path(result["original_path"]).parent == dirs["original"]
        assert splitter.validate_chunks(result["chunk_files"]) == (True, [])

    def test_split_file_splits_dict_groups_prefixes_and_reconstructs(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        splitter = JSONFileSplitter(size_threshold=70)
        source = tmp_path / "large-dict.json"
        original_data = {
            "pages": [{"name": "page"}],
            "rules": [{"name": "rule"}],
            "order_one": "a" * 30,
            "order_two": "b" * 30,
            "single": "c" * 30,
        }
        source.write_text(json.dumps(original_data), encoding="utf-8")

        result = splitter.split_file(str(source))
        reconstructed = tmp_path / "reconstructed.json"
        rebuilt = splitter.reconstruct_file(result["chunk_files"], str(reconstructed))

        assert result["success"] is True
        assert rebuilt is True
        assert json.loads(reconstructed.read_text(encoding="utf-8"))
        assert all(Path(path).parent == dirs["chunks"] for path in result["chunk_files"])

    def test_validate_chunks_reports_missing_fields_bad_json_and_bad_index(self, tmp_path, monkeypatch):
        _patch_path_manager(monkeypatch, tmp_path / "kb")
        splitter = JSONFileSplitter(size_threshold=50)
        missing = tmp_path / "missing.json"
        missing.write_text(json.dumps({"chunk_index": 0, "total_chunks": 1}), encoding="utf-8")
        bad_index = tmp_path / "bad_index.json"
        bad_index.write_text(json.dumps({"chunk_index": 2, "total_chunks": 1, "data": {}}), encoding="utf-8")
        bad_json = tmp_path / "bad_json.json"
        bad_json.write_text("{bad", encoding="utf-8")

        valid, errors = splitter.validate_chunks([str(missing), str(bad_index), str(bad_json)])

        assert valid is False
        assert len(errors) == 3

    def test_split_file_error_paths_and_helpers(self, tmp_path, monkeypatch):
        _patch_path_manager(monkeypatch, tmp_path / "kb")
        splitter = JSONFileSplitter(size_threshold=1)
        invalid = tmp_path / "invalid.json"
        invalid.write_text("{bad", encoding="utf-8")
        scalar = tmp_path / "scalar.json"
        scalar.write_text(json.dumps("not supported"), encoding="utf-8")

        assert splitter.split_file(str(tmp_path / "missing.json"))["success"] is False
        assert splitter.split_file(str(invalid))["success"] is False
        assert splitter.split_file(str(scalar))["success"] is False
        assert splitter._extract_prefix("orderStatus") == "order"
        assert splitter._extract_prefix("order_status") == "order"
        assert splitter._extract_prefix("plain") is None
        assert splitter._validate_json({"ok": True}) is True

    def test_split_file_cli_adds_validation_and_integrity_keys(self, tmp_path, monkeypatch):
        _patch_path_manager(monkeypatch, tmp_path / "kb")
        source = tmp_path / "cli.json"
        source.write_text(json.dumps([{"value": "x" * 40}, {"value": "y" * 40}]), encoding="utf-8")

        result = split_file_cli(str(source), size_threshold=50)

        assert result["success"] is True
        assert result["validation_passed"] is True
        assert "integrity_check" in result


class TestIndexBuilderV3:
    def test_process_file_json_and_markdown_builds_file_indexes(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        (dirs["original"] / "Doc One.json").write_text(
            json.dumps({"title": "Order API API API", "body": "customer order approval"}), encoding="utf-8"
        )
        (dirs["original"] / "Guide.md").write_text("# Guide\norder order customer workflow", encoding="utf-8")
        registry = {
            "files": {
                "doc_one": {"title": "Doc One", "tags": ["sales"], "classification": "docs", "hash": "hash1"},
                "guide": {"title": "Guide", "tags": ["guide"], "classification": "docs", "hash": "hash2"},
            }
        }
        dirs["metadata"].mkdir(exist_ok=True)
        (dirs["metadata"] / "file_registry.json").write_text(json.dumps(registry), encoding="utf-8")
        builder = IndexBuilderV3()

        result = builder.build_file_indexes()

        assert result["success"] is True
        assert result["processed_files"] == 2
        assert set(builder.list_existing_indexes()) == {"doc_one_index.json", "guide_index.json"}

    def test_build_global_index_and_clear_all_indexes(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        builder = IndexBuilderV3()
        index_payload = {
            "file_id": "file1",
            "filename": "file1.json",
            "title": "File 1",
            "classification": "class-a",
            "tags": ["tag-a"],
            "summary": "summary",
            "file_size": 12,
            "last_modified": 123,
        }
        builder.save_index(index_payload, "file1_index.json")

        global_result = builder.build_global_index()
        global_data = json.loads((dirs["index"] / "global" / "global_index.json").read_text(encoding="utf-8"))
        clear_result = builder.clear_all_indexes()

        assert global_result["success"] is True
        assert global_result["indexed_files"] == 1
        assert global_data["tags"]["tag-a"] == ["file1"]
        assert clear_result["success"] is True
        assert clear_result["deleted_files"] >= 1

    def test_build_file_indexes_handles_missing_dir_filter_and_unsupported_file(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        builder = IndexBuilderV3()
        builder.original_dir = str(tmp_path / "missing")
        assert builder.build_file_indexes()["success"] is False

        builder.original_dir = str(dirs["original"])
        (dirs["original"] / "keep.json").write_text(json.dumps({"order": "x"}), encoding="utf-8")
        (dirs["original"] / "skip.md").write_text("skip", encoding="utf-8")
        result = builder.build_file_indexes(file_filter="keep")

        assert result["total_files"] == 1
        assert result["processed_files"] == 1
        assert builder._process_file("unsupported.txt")["success"] is False

    def test_inverted_index_builds_compressed_index_and_optimizes_weights(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        chunk = {
            "chunk_id": "chunk-1",
            "metadata": {"module": "sales", "rule_id": "R1", "source_file": "source.json"},
            "content": {
                "rule_name": "Order approval",
                "rule_description": "Order customer customer",
                "original_rule": {"a": "approval workflow"},
            },
        }
        (dirs["chunks"] / "source_chunk_001.json").write_text(json.dumps(chunk), encoding="utf-8")
        builder = IndexBuilderV3()

        result = builder.build_inverted_index()

        assert result["success"] is True
        assert result["indexed_chunks"] == 1
        assert (dirs["index"] / "inverted" / "inverted_index.json").exists()
        with gzip.open(dirs["index"] / "inverted" / "inverted_index.json.gz", "rt", encoding="utf-8") as f:
            compressed = json.load(f)
        assert compressed["total_keywords"] >= 1

    def test_build_index_save_index_and_progress(self, tmp_path, monkeypatch):
        dirs = _patch_path_manager(monkeypatch, tmp_path / "kb")
        source = dirs["original"] / "single.json"
        source.write_text(json.dumps({"order": "approval"}), encoding="utf-8")
        builder = IndexBuilderV3()

        missing = builder.build_index(str(tmp_path / "missing.json"))
        built = builder.build_index(str(source))
        saved_path = builder.save_index({"file_id": "manual", "value": 1})

        assert missing["success"] is False
        assert built["success"] is True
        assert Path(saved_path).exists()
        assert {"total_files", "processed_files", "failed_files", "current_file"}.issubset(builder.get_progress())


class TestKnowledgeBaseMonitor:
    def test_check_file_size_monitor_add_and_scan(self, tmp_path, monkeypatch):
        _patch_path_manager(monkeypatch, tmp_path / "kb")
        monkeypatch.setattr(kb_monitor, "find_project_root", lambda start: str(tmp_path))
        monitor = KnowledgeBaseMonitor(size_threshold=10)
        small = Path(monitor.ORIGINAL_DIR) / "small.json"
        small.parent.mkdir(parents=True, exist_ok=True)
        small.write_text(json.dumps({"x": 1}), encoding="utf-8")
        large = Path(monitor.ORIGINAL_DIR) / "large.json"
        large.write_text(json.dumps({"x": "y" * 30}), encoding="utf-8")
        index_file = Path(monitor.INDEX_DIR) / "files" / "large_index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("{}", encoding="utf-8")

        assert monitor.check_file_size(str(tmp_path / "missing.json"))["error"]
        assert monitor.monitor_add_file(str(small), auto_process=False)["success"] is True
        assert monitor.monitor_update_file(str(small), auto_process=False)["success"] is True
        scan = monitor.scan_all_files()
        assert scan["total_files"] == 2
        assert {item["file"] for item in scan["already_processed"]} == {"small.json", "large.json"}

    def test_process_file_complete_and_process_all_files_with_fakes(self, tmp_path, monkeypatch):
        _patch_path_manager(monkeypatch, tmp_path / "kb")
        monkeypatch.setattr(kb_monitor, "find_project_root", lambda start: str(tmp_path))
        monitor = KnowledgeBaseMonitor(size_threshold=1)
        source = Path(monitor.ORIGINAL_DIR) / "large.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps({"x": "y" * 30}), encoding="utf-8")

        class FakeSplitter:
            def __init__(self, success=True):
                self.success = success

            def split_file(self, file_path):
                return {"success": self.success, "original_path": file_path, "error": "split failed"}

        class FakeIndexBuilder:
            def __init__(self, success=True):
                self.success = success
                self.saved = False

            def build_index(self, file_path):
                return {"success": self.success, "index_data": {"file_id": "large"}, "error": "index failed"}

            def save_index(self, index_data):
                self.saved = True
                return "saved"

        monitor.splitter = FakeSplitter(success=True)
        monitor.index_builder = FakeIndexBuilder(success=True)
        assert monitor.process_file_complete(str(source))["success"] is True

        monitor.index_builder = FakeIndexBuilder(success=False)
        failed_index = monitor.process_file_complete(str(source))
        assert failed_index["success"] is False
        assert "index failed" in failed_index["error"]

        monitor.splitter = FakeSplitter(success=False)
        failed_split = monitor.process_file_complete(str(source))
        assert failed_split["success"] is False
        assert "split failed" in failed_split["error"]

    def test_file_size_hook_invokes_callbacks_and_ignores_callback_errors(self, tmp_path, monkeypatch):
        _patch_path_manager(monkeypatch, tmp_path / "kb")
        monkeypatch.setattr(kb_monitor, "find_project_root", lambda start: str(tmp_path))
        hook = FileSizeHook(size_threshold=10)
        source = tmp_path / "hook.json"
        source.write_text(json.dumps({"x": 1}), encoding="utf-8")
        calls = []

        hook.register_callback(lambda file_path, result: calls.append((file_path, result["success"])))
        hook.register_callback(lambda file_path, result: (_ for _ in ()).throw(RuntimeError("callback boom")))

        add_result = hook.on_file_add(str(source), auto_process=False)
        update_result = hook.on_file_update(str(source), auto_process=False)

        assert add_result["success"] is True
        assert update_result["success"] is True
        assert len(calls) == 2
