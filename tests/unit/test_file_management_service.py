from unittest.mock import patch

from modules.trae_test.utils.file_management_service import FileManagementService


class TestFileManagementService:

    def test_initialization(self):
        service = FileManagementService()
        assert service is not None

    def test_add_file_success(self):
        service = FileManagementService()

        with patch("modules.trae_test.utils.file_management_service.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.file_management_service.shutil.copy2"):
                with patch("modules.trae_test.utils.file_management_service.kb_monitor_module") as mock_monitor:
                    with patch("modules.trae_test.utils.file_management_service.metadata_manager_module"):
                        mock_monitor.KnowledgeBaseMonitor.return_value.process_file_complete.return_value = {
                            "success": True
                        }

                        result = service.add_file(
                            "test.json",
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

    def test_update_file_success(self):
        service = FileManagementService()

        with patch("modules.trae_test.utils.file_management_service.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.file_management_service.shutil.copy2"):
                with patch("modules.trae_test.utils.file_management_service.kb_monitor_module") as mock_monitor:
                    with patch("modules.trae_test.utils.file_management_service.metadata_manager_module"):
                        with patch(
                            "modules.trae_test.utils.file_management_service.os.listdir",
                            return_value=["test_chunk_001.json"],
                        ):
                            with patch("modules.trae_test.utils.file_management_service.os.remove"):
                                mock_monitor.KnowledgeBaseMonitor.return_value.process_file_complete.return_value = {
                                    "success": True
                                }

                                result = service.update_file(
                                    "test.json",
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

    def test_add_file_without_auto_process(self):
        service = FileManagementService()

        with patch("modules.trae_test.utils.file_management_service.os.path.exists", return_value=True):
            with patch("modules.trae_test.utils.file_management_service.shutil.copy2"):
                with patch("modules.trae_test.utils.file_management_service.metadata_manager_module"):
                    result = service.add_file("test.json", auto_process=False)

                    assert result["success"] is True
