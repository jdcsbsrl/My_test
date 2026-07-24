from unittest.mock import patch

from modules.trae_test.utils.file_management_service import FileManagementService


class TestFileManagementService:

    def _use_temp_kb_dirs(self, service, tmp_path):
        service.original_dir = str(tmp_path / "knowledge_base" / "data" / "original")
        service.chunks_dir = str(tmp_path / "knowledge_base" / "data" / "chunks")
        return service

    def _create_source_file(self, tmp_path, file_name="test.json"):
        source_file = tmp_path / "source" / file_name
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text('{"name": "test"}', encoding="utf-8")
        return source_file

    def test_initialization(self):
        service = FileManagementService()
        assert service is not None

    def test_add_file_success(self, tmp_path):
        service = self._use_temp_kb_dirs(FileManagementService(), tmp_path)
        source_file = self._create_source_file(tmp_path)

        with patch("modules.trae_test.utils.file_management_service.shutil.copy2"):
            with patch("modules.trae_test.utils.file_management_service.kb_monitor_module") as mock_monitor:
                with patch("modules.trae_test.utils.file_management_service.metadata_manager_module") as mock_meta:
                    mock_monitor.KnowledgeBaseMonitor.return_value.process_file_complete.return_value = {
                        "success": True
                    }
                    mock_meta.MetadataManager.return_value.scan_and_register_all.return_value = None

                    result = service.add_file(
                        str(source_file),
                        auto_process=True,
                        clear_caches_callback=lambda: None,
                        load_registry_callback=lambda: None,
                    )

                    assert result["success"] is True
                    assert result["file_title"] == "test"

    def test_add_file_not_found(self):
        service = FileManagementService()

        with patch("modules.trae_test.utils.file_management_service.os.path.exists", return_value=False):
            result = service.add_file("nonexistent.json")

            assert result["success"] is False
            assert "源文件不存在" in result["error"]

    def test_update_file_success(self, tmp_path):
        service = self._use_temp_kb_dirs(FileManagementService(), tmp_path)
        source_file = self._create_source_file(tmp_path)
        target_file = tmp_path / "knowledge_base" / "data" / "original" / "test.json"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text('{"name": "old"}', encoding="utf-8")

        with patch("modules.trae_test.utils.file_management_service.shutil.copy2"):
            with patch("modules.trae_test.utils.file_management_service.kb_monitor_module") as mock_monitor:
                with patch("modules.trae_test.utils.file_management_service.metadata_manager_module") as mock_meta:
                    with patch(
                        "modules.trae_test.utils.file_management_service.os.listdir",
                        return_value=["test_chunk_001.json"],
                    ):
                        with patch("modules.trae_test.utils.file_management_service.os.remove"):
                            mock_monitor.KnowledgeBaseMonitor.return_value.process_file_complete.return_value = {
                                "success": True
                            }
                            mock_meta.MetadataManager.return_value.scan_and_register_all.return_value = None

                            result = service.update_file(
                                str(source_file),
                                auto_process=True,
                                clear_caches_callback=lambda: None,
                                load_registry_callback=lambda: None,
                            )

                            assert result["success"] is True

    def test_update_file_not_found(self):
        service = FileManagementService()

        with patch("modules.trae_test.utils.file_management_service.os.path.exists") as mock_exists:
            mock_exists.side_effect = [True, False]
            result = service.update_file("nonexistent.json")

            assert result["success"] is False
            assert "知识库中不存在该文件" in result["error"]

    def test_add_file_without_auto_process(self, tmp_path):
        service = self._use_temp_kb_dirs(FileManagementService(), tmp_path)
        source_file = self._create_source_file(tmp_path)

        with patch("modules.trae_test.utils.file_management_service.shutil.copy2"):
            with patch("modules.trae_test.utils.file_management_service.metadata_manager_module") as mock_meta:
                mock_meta.MetadataManager.return_value.scan_and_register_all.return_value = None
                result = service.add_file(str(source_file), auto_process=False)

                assert result["success"] is True
