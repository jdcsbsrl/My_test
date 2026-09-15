from types import SimpleNamespace

from tools.kb_manager import KnowledgeBaseManager


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
