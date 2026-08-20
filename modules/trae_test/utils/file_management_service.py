"""知识库文件管理服务"""

import os
import shutil
import tempfile
from typing import Any

import modules.trae_test.utils.kb_monitor as kb_monitor_module
import modules.trae_test.utils.metadata_manager as metadata_manager_module
from .index_builder_v3 import IndexBuilderV3

from .path_utils import PathManager, is_chunk_filename


class FileManagementService:
    """文件管理服务 - 提供文件的添加、更新等管理功能"""

    def __init__(self, kb_base_dir: str | None = None):
        self.kb_base_dir = os.path.abspath(kb_base_dir) if kb_base_dir else None
        if self.kb_base_dir:
            self.original_dir = os.path.join(self.kb_base_dir, "data", "original")
            self.chunks_dir = os.path.join(self.kb_base_dir, "data", "chunks")
        else:
            self.original_dir = PathManager.get_original_dir()
            self.chunks_dir = PathManager.get_chunks_dir()
        PathManager.ensure_directories(self.original_dir, self.chunks_dir)

    def _snapshot(self, target_path: str, file_title: str) -> tuple[str, list[str], str | None]:
        """Create a recoverable snapshot before a mutating operation."""
        snapshot_dir = tempfile.mkdtemp(prefix="kb-file-operation-")
        old_target = os.path.join(snapshot_dir, "original")
        if os.path.exists(target_path):
            shutil.copy2(target_path, old_target)
        else:
            old_target = ""
        old_chunks: list[str] = []
        for chunk_path in self._get_existing_chunks(file_title):
            backup = os.path.join(snapshot_dir, os.path.basename(chunk_path))
            shutil.copy2(chunk_path, backup)
            old_chunks.append(backup)
        return snapshot_dir, old_chunks, old_target or None

    def _restore_snapshot(self, snapshot_dir: str, target_path: str, old_chunks: list[str], old_target: str | None, file_title: str) -> None:
        """Restore original and chunks; best effort with explicit cleanup."""
        if old_target:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(old_target, target_path)
        elif os.path.exists(target_path):
            os.unlink(target_path)
        for chunk_path in self._get_existing_chunks(file_title):
            try:
                os.unlink(chunk_path)
            except OSError:
                pass
        for backup in old_chunks:
            shutil.copy2(backup, os.path.join(self.chunks_dir, os.path.basename(backup)))

    def _rebuild_secondary_indexes(self) -> None:
        """Refresh global and inverted indexes after registry mutation."""
        builder = IndexBuilderV3()
        global_result = builder.build_global_index()
        if not global_result.get("success", False):
            raise RuntimeError(global_result.get("error", "全局索引更新失败"))
        inverted_result = builder.build_inverted_index()
        if not inverted_result.get("success", False):
            raise RuntimeError(inverted_result.get("error", "倒排索引更新失败"))

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
            if os.path.exists(target_path):
                result["error"] = f"知识库中已存在该文件: {target_path}，请使用 update_file() 更新"
                return result
            snapshot_dir, old_chunks, old_target = self._snapshot(target_path, file_title)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(file_path, target_path)
            if auto_process:
                    monitor = kb_monitor_module.KnowledgeBaseMonitor()
                    process_result = monitor.process_file_complete(target_path)
                    result["process_result"] = process_result
                    if not process_result.get("success", False):
                        result["error"] = process_result.get("error", "处理失败")
                        return result

            meta = metadata_manager_module.MetadataManager(self.kb_base_dir)
            registry_result = meta.scan_and_register_all()
            if registry_result is not None and not registry_result.get("success", False):
                raise RuntimeError(registry_result.get("error", "注册表更新失败"))
            self._rebuild_secondary_indexes()
            if clear_caches_callback:
                clear_caches_callback()
            if load_registry_callback:
                load_registry_callback()
            result["success"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            return result
        finally:
            if 'snapshot_dir' in locals():
                if not result["success"]:
                    try:
                        self._restore_snapshot(snapshot_dir, target_path, old_chunks, old_target, file_title)
                    except Exception as restore_error:
                        result["restore_error"] = str(restore_error)
                shutil.rmtree(snapshot_dir, ignore_errors=True)

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

            snapshot_dir, old_chunks, old_target = self._snapshot(target_path, file_title)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(file_path, target_path)

            if auto_process:
                monitor = kb_monitor_module.KnowledgeBaseMonitor()
                process_result = monitor.process_file_complete(target_path)
                result["process_result"] = process_result

                if process_result["success"]:
                    meta = metadata_manager_module.MetadataManager(self.kb_base_dir)
                    registry_result = meta.scan_and_register_all()
                    if registry_result is not None and not registry_result.get("success", False):
                        raise RuntimeError(registry_result.get("error", "注册表更新失败"))
                    self._rebuild_secondary_indexes()
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
        finally:
            if 'snapshot_dir' in locals():
                if not result["success"]:
                    try:
                        self._restore_snapshot(snapshot_dir, target_path, old_chunks, old_target, file_title)
                    except Exception as restore_error:
                        result["restore_error"] = str(restore_error)
                shutil.rmtree(snapshot_dir, ignore_errors=True)

    def _get_existing_chunks(self, file_title: str) -> list:
        """获取文件已有的所有分块路径

        Args:
            file_title: 文件标题

        Returns:
            分块文件路径列表
        """
        existing = []
        normalized_title = file_title.replace(" ", "_").lower()
        valid_prefixes = (file_title + "_", normalized_title + "_")
        if os.path.exists(self.chunks_dir):
            for fname in os.listdir(self.chunks_dir):
                if is_chunk_filename(fname) and fname.startswith(valid_prefixes):
                    existing.append(os.path.join(self.chunks_dir, fname))
        return existing
