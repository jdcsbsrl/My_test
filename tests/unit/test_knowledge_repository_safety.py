import json

from modules.trae_test.utils.file_repository import FileRepository


def test_repository_uses_custom_knowledge_base_and_virtual_chunk(tmp_path):
    original = tmp_path / "data" / "original"
    original.mkdir(parents=True)
    source = original / "small.json"
    source.write_text(json.dumps({"value": 1}), encoding="utf-8")
    repo = FileRepository(str(tmp_path))

    chunks = repo.get_all_chunks("small")
    assert len(chunks) == 1
    assert chunks[0]["data"] == {"value": 1}
    assert repo.load_aggregated_data("small") == {"value": 1}


def test_repository_cache_invalidates_when_source_changes(tmp_path):
    original = tmp_path / "data" / "original"
    original.mkdir(parents=True)
    source = original / "small.json"
    source.write_text(json.dumps({"value": 1}), encoding="utf-8")
    repo = FileRepository(str(tmp_path))
    info = {"file_id": "small", "original_path": "data/original/small.json"}

    assert repo.load_file(info)["value"] == 1
    source.write_text(json.dumps({"value": 2}), encoding="utf-8")
    assert repo.load_file(info)["value"] == 2
