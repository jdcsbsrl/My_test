import json
from unittest.mock import patch

from modules.trae_test.utils.file_repository import FileRepository


class TestFileRepository:

    def test_initialization(self):
        repo = FileRepository()
        assert repo is not None

    def test_load_file_with_cache(self):
        repo = FileRepository()
        mock_file_info = {"file_id": "test_file", "original_path": "data/original/test.json", "title": "Test"}

        with patch("modules.trae_test.utils.file_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.file_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"content": "test"})

                result = repo.load_file(mock_file_info)
                assert result is not None
                assert result["content"] == "test"

                result2 = repo.load_file(mock_file_info)
                assert result2 == result

    def test_load_file_not_found(self):
        repo = FileRepository()
        mock_file_info = {"file_id": "nonexistent", "original_path": "data/original/nonexistent.json"}

        with patch("modules.trae_test.utils.file_repository.os.path.exists", return_value=False):
            result = repo.load_file(mock_file_info)
            assert result is None

    def test_clear_cache(self):
        repo = FileRepository()
        mock_file_info = {"file_id": "test_file", "original_path": "data/original/test.json", "title": "Test"}

        with patch("modules.trae_test.utils.file_repository.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.file_repository.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({"content": "test"})
                repo.load_file(mock_file_info)
                assert repo.get_file_cache_size() == 1

                repo.clear_cache()
                assert repo.get_file_cache_size() == 0

    def test_get_file_cache_size(self):
        repo = FileRepository()
        assert repo.get_file_cache_size() == 0
