import json

from modules.trae_test.utils.metadata_manager import MetadataManager


def _write(path, title):
    path.write_text(json.dumps({"title": title, "business_rules": []}), encoding="utf-8")


def test_scan_refuses_to_overwrite_registry_when_files_disappear(tmp_path):
    kb = tmp_path / "kb"
    original = kb / "data" / "original"
    original.mkdir(parents=True)
    _write(original / "a.json", "a")
    _write(original / "b.json", "b")
    manager = MetadataManager(str(kb))

    first = manager.scan_and_register_all(str(original))
    assert first["success"] is True
    assert first["registered_files"] == 2

    (original / "b.json").unlink()
    blocked = manager.scan_and_register_all(str(original))
    assert blocked["success"] is False
    registry = manager.load_registry()
    assert len(registry["files"]) == 2


def test_scan_allows_explicit_shrink(tmp_path):
    kb = tmp_path / "kb"
    original = kb / "data" / "original"
    original.mkdir(parents=True)
    _write(original / "a.json", "a")
    _write(original / "b.json", "b")
    manager = MetadataManager(str(kb))
    manager.scan_and_register_all(str(original))
    (original / "b.json").unlink()

    result = manager.scan_and_register_all(str(original), allow_shrink=True)
    assert result["success"] is True
    assert len(manager.load_registry()["files"]) == 1
