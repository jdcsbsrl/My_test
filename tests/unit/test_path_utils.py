import os

from modules.trae_test.utils.path_utils import PathManager


class TestPathUtils:

    def test_get_kb_base_dir(self):
        base_dir = PathManager.get_kb_base_dir()
        assert isinstance(base_dir, str)
        assert "assets" in base_dir or "knowledge_base" in base_dir

    def test_get_data_dir(self):
        data_dir = PathManager.get_data_dir()
        assert isinstance(data_dir, str)
        assert os.path.basename(data_dir) == "data"

    def test_get_original_dir(self):
        original_dir = PathManager.get_original_dir()
        assert isinstance(original_dir, str)
        assert os.path.basename(original_dir) == "original"

    def test_get_chunks_dir(self):
        chunks_dir = PathManager.get_chunks_dir()
        assert isinstance(chunks_dir, str)
        assert os.path.basename(chunks_dir) == "chunks"

    def test_get_index_dir(self):
        index_dir = PathManager.get_index_dir()
        assert isinstance(index_dir, str)
        assert os.path.basename(index_dir) == "index"

    def test_get_metadata_dir(self):
        metadata_dir = PathManager.get_metadata_dir()
        assert isinstance(metadata_dir, str)
        assert os.path.basename(metadata_dir) == "metadata"

    def test_ensure_directories(self, tmp_path):
        test_dir = os.path.join(str(tmp_path), "test_dir", "sub_dir")
        assert not os.path.exists(test_dir)

        PathManager.ensure_directories(test_dir)
        assert os.path.exists(test_dir)

    def test_ensure_kb_directories(self):
        PathManager.ensure_kb_directories()

        assert os.path.exists(PathManager.get_kb_base_dir())
        assert os.path.exists(PathManager.get_data_dir())
        assert os.path.exists(PathManager.get_original_dir())
        assert os.path.exists(PathManager.get_chunks_dir())
        assert os.path.exists(PathManager.get_index_dir())
        assert os.path.exists(PathManager.get_metadata_dir())

    def test_path_consistency(self):
        base_dir = PathManager.get_kb_base_dir()

        assert PathManager.get_data_dir().startswith(base_dir)
        assert PathManager.get_original_dir().startswith(base_dir)
        assert PathManager.get_chunks_dir().startswith(base_dir)
        assert PathManager.get_index_dir().startswith(base_dir)
        assert PathManager.get_metadata_dir().startswith(base_dir)
