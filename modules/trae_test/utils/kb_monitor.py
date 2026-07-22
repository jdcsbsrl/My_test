"""知识库监控模块，实现文件大小监控和自动分割触发"""

import os
from collections.abc import Callable
from typing import Any

from .file_splitter import JSONFileSplitter
from .index_builder_v3 import IndexBuilderV3
from .path_utils import find_project_root


class KnowledgeBaseMonitor:
    """知识库监控器，监控文件变更并触发自动处理"""

    SIZE_THRESHOLD = 80 * 1024

    def __init__(self, size_threshold: int = None):
        """初始化监控器

        Args:
            size_threshold: 文件大小阈值（字节），默认为80KB
        """
        self.size_threshold = size_threshold if size_threshold else self.SIZE_THRESHOLD
        project_root = find_project_root(__file__)
        self.KB_BASE_DIR = os.path.join(project_root, "assets", "knowledge_base")
        self.DATA_DIR = os.path.join(self.KB_BASE_DIR, "data")
        self.ORIGINAL_DIR = os.path.join(self.DATA_DIR, "original")
        self.CONTENT_DIR = os.path.join(self.DATA_DIR, "chunks")
        self.INDEX_DIR = os.path.join(self.KB_BASE_DIR, "index")
        self.splitter = JSONFileSplitter(self.size_threshold)
        self.index_builder = IndexBuilderV3()
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        for dir_path in [self.KB_BASE_DIR, self.ORIGINAL_DIR, self.CONTENT_DIR, self.INDEX_DIR]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

    def check_file_size(self, file_path: str) -> dict[str, Any]:
        """检查文件大小是否超过阈值

        Args:
            file_path: 文件路径

        Returns:
            检查结果字典
        """
        result = {
            "file_path": file_path,
            "file_size": 0,
            "exceeds_threshold": False,
            "threshold": self.size_threshold,
            "error": "",
        }

        try:
            if not os.path.exists(file_path):
                result["error"] = f"文件不存在: {file_path}"
                return result

            file_size = os.path.getsize(file_path)
            result["file_size"] = file_size
            result["exceeds_threshold"] = file_size > self.size_threshold

            return result
        except Exception as e:
            result["error"] = str(e)
            return result

    def monitor_add_file(self, file_path: str, auto_process: bool = True) -> dict[str, Any]:
        """监控添加文件操作

        Args:
            file_path: 要添加的文件路径
            auto_process: 是否自动处理（分割+索引）

        Returns:
            处理结果字典
        """
        result = {
            "success": False,
            "file_path": file_path,
            "size_check": None,
            "split_result": None,
            "index_result": None,
            "error": "",
        }

        try:
            size_check = self.check_file_size(file_path)
            result["size_check"] = size_check

            if size_check.get("error"):
                result["error"] = size_check["error"]
                return result

            if auto_process and size_check["exceeds_threshold"]:
                split_result = self.splitter.split_file(file_path)
                result["split_result"] = split_result

                if split_result["success"]:
                    index_result = self.index_builder.build_index(split_result["original_path"])
                    if index_result["success"]:
                        self.index_builder.save_index(index_result["index_data"])
                    result["index_result"] = index_result

            result["success"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def monitor_update_file(self, file_path: str, auto_process: bool = True) -> dict[str, Any]:
        """监控更新文件操作

        Args:
            file_path: 要更新的文件路径
            auto_process: 是否自动处理（分割+索引）

        Returns:
            处理结果字典
        """
        return self.monitor_add_file(file_path, auto_process)

    def scan_all_files(self) -> dict[str, Any]:
        """扫描所有知识库文件，检查是否需要处理

        Returns:
            扫描结果字典
        """
        result = {"total_files": 0, "needs_processing": [], "already_processed": [], "errors": []}

        if not os.path.exists(self.ORIGINAL_DIR):
            return result

        for filename in os.listdir(self.ORIGINAL_DIR):
            if filename.endswith(".json"):
                file_path = os.path.join(self.ORIGINAL_DIR, filename)
                result["total_files"] += 1

                size_check = self.check_file_size(file_path)
                if size_check.get("error"):
                    result["errors"].append({"file": filename, "error": size_check["error"]})
                    continue

                file_title = os.path.splitext(filename)[0]
                index_file = f"{file_title}_index.json"
                index_exists = os.path.exists(os.path.join(self.INDEX_DIR, index_file))

                if size_check["exceeds_threshold"] and not index_exists:
                    result["needs_processing"].append({"file": filename, "file_size": size_check["file_size"]})
                else:
                    result["already_processed"].append({"file": filename, "file_size": size_check["file_size"]})

        return result

    def process_file_complete(self, file_path: str) -> dict[str, Any]:
        """完整处理单个文件：备份 -> 分割 -> 索引

        Args:
            file_path: 文件路径

        Returns:
            处理结果字典
        """
        result = {"success": False, "file_path": file_path, "split": None, "index": None, "error": ""}

        try:
            split_result = self.splitter.split_file(file_path)
            result["split"] = split_result

            if not split_result["success"]:
                result["error"] = f"分割失败: {split_result['error']}"
                return result

            index_result = self.index_builder.build_index(split_result["original_path"])
            result["index"] = index_result

            if index_result["success"]:
                self.index_builder.save_index(index_result["index_data"])
                result["success"] = True
            else:
                result["error"] = f"索引失败: {index_result['error']}"

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def process_all_files(self) -> dict[str, Any]:
        """完整处理所有需要处理的文件

        Returns:
            处理结果字典
        """
        result = {"success": True, "processed": [], "failed": [], "skipped": []}

        scan_result = self.scan_all_files()

        for item in scan_result["needs_processing"]:
            file_path = os.path.join(self.ORIGINAL_DIR, item["file"])
            process_result = self.process_file_complete(file_path)

            if process_result["success"]:
                result["processed"].append(item["file"])
            else:
                result["failed"].append({"file": item["file"], "error": process_result["error"]})

        result["skipped"] = [item["file"] for item in scan_result["already_processed"]]

        return result


class FileSizeHook:
    """文件大小监控钩子，可集成到文件操作流程中"""

    def __init__(self, size_threshold: int = 80 * 1024):
        """初始化钩子

        Args:
            size_threshold: 大小阈值（字节）
        """
        self.size_threshold = size_threshold
        self.monitor = KnowledgeBaseMonitor(size_threshold)
        self.callbacks: list[Callable] = []

    def register_callback(self, callback: Callable[[str, dict[str, Any]], None]):
        """注册回调函数

        Args:
            callback: 回调函数，接收(file_path, check_result)
        """
        self.callbacks.append(callback)

    def on_file_add(self, file_path: str, auto_process: bool = True) -> dict[str, Any]:
        """文件添加时触发

        Args:
            file_path: 文件路径
            auto_process: 是否自动处理

        Returns:
            处理结果
        """
        result = self.monitor.monitor_add_file(file_path, auto_process)

        for callback in self.callbacks:
            try:
                callback(file_path, result)
            except Exception as e:
                print(f"回调执行错误: {e}")

        return result

    def on_file_update(self, file_path: str, auto_process: bool = True) -> dict[str, Any]:
        """文件更新时触发

        Args:
            file_path: 文件路径
            auto_process: 是否自动处理

        Returns:
            处理结果
        """
        result = self.monitor.monitor_update_file(file_path, auto_process)

        for callback in self.callbacks:
            try:
                callback(file_path, result)
            except Exception as e:
                print(f"回调执行错误: {e}")

        return result
