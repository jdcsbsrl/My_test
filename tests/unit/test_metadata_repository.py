import json
from unittest.mock import patch

from modules.trae_test.utils.metadata_repository import MetadataRepository


class TestMetadataRepository:

    def test_initialization(self):
        repo = MetadataRepository()
        assert repo is not None

    def test_load_registry(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    {"files": {"file1": {"title": "Test", "original_path": "test.json"}}, "tags": {"tag1": ["file1"]}}
                )

                repo.load_registry()
                assert repo.get_registry() is not None

    def test_get_file_by_id(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    {"files": {"file1": {"title": "Test", "original_path": "test.json"}}, "tags": {}}
                )

                result = repo.get_file_by_id("file1")
                assert result is not None
                assert result["title"] == "Test"

    def test_get_file_by_id_nonexistent(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"files": {}, "tags": {}})

                result = repo.get_file_by_id("nonexistent")
                assert result is None

    def test_get_files_by_tag(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    {"files": {"file1": {"title": "Test", "original_path": "test.json"}}, "tags": {"tag1": ["file1"]}}
                )

                result = repo.get_files_by_tag("tag1")
                assert isinstance(result, list)
                assert len(result) == 1

    def test_search_by_tags(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    {
                        "files": {"file1": {"title": "Test", "original_path": "test.json"}},
                        "tags": {"tag1": ["file1"], "tag2": ["file1"]},
                    }
                )

                result = repo.search_by_tags("tag1", "tag2")
                assert isinstance(result, list)
                assert len(result) == 1

    def test_list_available_files(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    {"files": {"file1": {"title": "Test"}, "file2": {"title": "Test2"}}, "tags": {}}
                )

                result = repo.list_available_files()
                assert isinstance(result, list)
                assert len(result) == 2

    def test_get_registry_stats(self):
        repo = MetadataRepository()

        with patch("modules.trae_test.utils.metadata_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.metadata_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    {"files": {"file1": {"title": "Test"}}, "tags": {"tag1": ["file1"]}}
                )

                repo.load_registry()
                stats = repo.get_registry_stats()
                assert stats["total_files"] == 1
                assert stats["total_tags"] == 1

    def test_clear_rule_index(self):
        repo = MetadataRepository()
        repo._rule_file_index = [{"file_id": "test"}]
        repo._rules_loaded = True

        repo.clear_rule_index()
        assert len(repo._rule_file_index) == 0
        assert repo._rules_loaded is False
