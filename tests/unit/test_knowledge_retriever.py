from unittest.mock import patch

from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever


class TestKnowledgeRetriever:

    def test_initialization(self):
        retriever = KnowledgeRetriever()
        assert retriever is not None
        assert retriever.knowledge_base_dir is not None
        assert retriever._registry is not None

    def test_load_registry(self):
        retriever = KnowledgeRetriever()
        assert retriever._registry is not None

    def test_get_file_by_id(self):
        retriever = KnowledgeRetriever()
        if retriever._registry and retriever._registry.get("files"):
            first_file_id = next(iter(retriever._registry["files"].keys()))
            file_info = retriever._get_file_by_id(first_file_id)
            assert file_info is not None
            assert "title" in file_info
        else:
            result = retriever._get_file_by_id("nonexistent")
            assert result is None

    def test_get_file_by_id_nonexistent(self):
        retriever = KnowledgeRetriever()
        result = retriever._get_file_by_id("nonexistent_id_12345")
        assert result is None

    def test_get_files_by_tag(self):
        retriever = KnowledgeRetriever()
        files = retriever._get_files_by_tag("业务规则")
        assert isinstance(files, list)

    def test_get_files_by_tag_nonexistent(self):
        retriever = KnowledgeRetriever()
        files = retriever._get_files_by_tag("不存在的标签")
        assert isinstance(files, list)
        assert len(files) == 0

    def test_ensure_rules_loaded(self):
        retriever = KnowledgeRetriever()
        retriever._ensure_rules_loaded()
        assert retriever._rules_loaded is True

    def test_api_version_auto(self):
        retriever = KnowledgeRetriever(api_version="auto")
        assert retriever is not None

    def test_api_version_explicit(self):
        retriever = KnowledgeRetriever(api_version="3.0.0")
        assert retriever is not None

    @patch("modules.trae_test.utils.knowledge_retriever.os.getenv")
    def test_db_disabled(self, mock_getenv):
        mock_getenv.return_value = None
        retriever = KnowledgeRetriever()
        assert retriever._db_enabled is False

    @patch("modules.trae_test.utils.knowledge_retriever.os.getenv")
    def test_db_enabled(self, mock_getenv):
        mock_getenv.return_value = "postgresql://localhost/test"
        retriever = KnowledgeRetriever()
        assert retriever._db_enabled is True

    def test_file_cache_initialized(self):
        retriever = KnowledgeRetriever()
        assert isinstance(retriever._file_cache, dict)

    def test_index_cache_initialized(self):
        retriever = KnowledgeRetriever()
        assert isinstance(retriever._index_cache, dict)
