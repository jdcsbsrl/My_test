"""知识库文件管理服务"""

import os
import shutil
from typing import Any

import modules.trae_test.utils.kb_monitor as kb_monitor_module
import modules.trae_test.utils.metadata_manager as metadata_manager_module

from .path_utils import PathManager, is_chunk_filename


class FileManagementService:
    """文件管理服务 - 提供文件的添加、更新等管理功能"""

    def __init__(self):
        self.original_dir = PathManager.get_original_dir()
        self.chunks_dir = PathManager.get_chunks_dir()
        PathManager.ensure_directories(self.original_dir, self.chunks_dir)

    def add_file(
        self, file_path: str, auto_process: bool = True, clear_caches_callback=None, load_registry_callback=None
    ) -> dict[str, Any]:
        """添加新文件到知识库

        将文件复制到 data/original/ 目录，自动触发分割和索引构建，
        并更新文件注册表。

        Args:
            file_path: 源文件路径
            auto_process: 是否自动处理（分割+索引）
            clear_caches_callback: 清除缓存的回调函数
            load_registry_callback: 重新加载注册表的回调函数

        Returns:
            处理结果字典，包含 success、file_title、split_result、index_result 等字段
        """
        result = {"success": False, "file_path": file_path, "file_title": "", "error": ""}

        try:
            if not os.path.exists(file_path):
                result["error"] = f"源文件不存在: {file_path}"
                return result

            file_name = os.path.basename(file_path)
            file_title = os.path.splitext(file_name)[0]
            result["file_title"] = file_title

            target_path = os.path.join(self.original_dir, file_name)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(file_path, target_path)

            if auto_process:
                monitor = kb_monitor_module.KnowledgeBaseMonitor()
                process_result = monitor.process_file_complete(target_path)
                result["process_result"] = process_result

                if process_result["success"]:
                    meta = metadata_manager_module.MetadataManager()
                    meta.scan_and_register_all()
                    if clear_caches_callback:
                        clear_caches_callback()
                    if load_registry_callback:
                        load_registry_callback()
                    result["success"] = True
                else:
                    result["error"] = process_result.get("error", "处理失败")
            else:
                meta = metadata_manager_module.MetadataManager()
                meta.scan_and_register_all()
                if clear_caches_callback:
                    clear_caches_callback()
                if load_registry_callback:
                    load_registry_callback()
                result["success"] = True

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def update_file(
        self, file_path: str, auto_process: bool = True, clear_caches_callback=None, load_registry_callback=None
    ) -> dict[str, Any]:
        """更新现有文件并重建索引

        覆盖 data/original/ 中的对应文件，重新分割并重建索引，
        同步更新文件注册表。

        Args:
            file_path: 源文件路径（用于更新知识库中的对应文件）
            auto_process: 是否自动处理（分割+索引）
            clear_caches_callback: 清除缓存的回调函数
            load_registry_callback: 重新加载注册表的回调函数

        Returns:
            处理结果字典
        """
        result = {"success": False, "file_path": file_path, "file_title": "", "error": ""}

        try:
            if not os.path.exists(file_path):
                result["error"] = f"源文件不存在: {file_path}"
                return result

            file_name = os.path.basename(file_path)
            file_title = os.path.splitext(file_name)[0]
            target_path = os.path.join(self.original_dir, file_name)
            result["file_title"] = file_title

            if not os.path.exists(target_path):
                result["error"] = f"知识库中不存在该文件: {target_path}，请使用 add_file() 添加"
                return result

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(file_path, target_path)

            if auto_process:
                old_chunks = self._get_existing_chunks(file_title)
                for chunk_path in old_chunks:
                    try:
                        os.remove(chunk_path)
                    except Exception as e:
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.warning(f"Failed to remove chunk {chunk_path}: {e}")

                monitor = kb_monitor_module.KnowledgeBaseMonitor()
                process_result = monitor.process_file_complete(target_path)
                result["process_result"] = process_result

                if process_result["success"]:
                    meta = metadata_manager_module.MetadataManager()
                    meta.scan_and_register_all()
                    if clear_caches_callback:
                        clear_caches_callback()
                    if load_registry_callback:
                        load_registry_callback()
                    result["success"] = True
                else:
                    result["error"] = process_result.get("error", "处理失败")
            else:
                result["success"] = True

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def _get_existing_chunks(self, file_title: str) -> list:
        """获取文件已有的所有分块路径

        Args:
            file_title: 文件标题

        Returns:
            分块文件路径列表
        """
        existing = []
        if os.path.exists(self.chunks_dir):
            for fname in os.listdir(self.chunks_dir):
                if is_chunk_filename(fname):
                    existing.append(os.path.join(self.chunks_dir, fname))
        return existing
