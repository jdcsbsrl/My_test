"""知识库数据访问层 - 文件仓储"""

import json
import os
from typing import Any

from .path_utils import PathManager, is_chunk_filename


class FileRepository:
    """文件仓储 - 提供文件内容的加载和缓存功能"""

    def __init__(self, kb_base_dir: str = None):
        self.kb_base_dir = kb_base_dir or PathManager.get_kb_base_dir()
        self.original_dir = PathManager.get_original_dir()
        self.chunks_dir = PathManager.get_chunks_dir()

        self._file_cache = {}
        self._index_cache = {}

    def load_file(self, file_info: dict[str, Any]) -> dict[str, Any] | None:
        """加载文件内容（支持JSON和MD文件）

        Args:
            file_info: 文件信息字典，包含file_id和original_path

        Returns:
            文件内容字典，未找到返回None
        """
        file_id = file_info.get("file_id")
        if file_id in self._file_cache:
            return self._file_cache[file_id]

        original_path = file_info.get("original_path")
        if not original_path:
            return None

        full_path = os.path.join(self.kb_base_dir, original_path)
        if os.path.exists(full_path):
            try:
                if original_path.lower().endswith(".json"):
                    with open(full_path, encoding="utf-8") as f:
                        content = json.load(f)
                elif original_path.lower().endswith(".md"):
                    with open(full_path, encoding="utf-8") as f:
                        raw_text = f.read()
                    content = {"title": file_info.get("title", ""), "raw_markdown": raw_text}
                else:
                    return None
                self._file_cache[file_id] = content
                return content
            except Exception as e:
                print(f"[FileRepository] 加载文件失败 {full_path}: {e}")

        return None

    def get_all_chunks(self, file_title: str) -> list[dict[str, Any]]:
        """获取文件的所有内容块

        Args:
            file_title: 文件标题（如 销售模块、需求清单）

        Returns:
            块数据列表，按 chunk_index 排序
        """
        chunks = []

        if not os.path.exists(self.chunks_dir):
            return chunks

        normalized_title = file_title.replace(" ", "_").lower()
        valid_prefixes = (file_title + "_", normalized_title + "_")

        for filename in os.listdir(self.chunks_dir):
            if is_chunk_filename(filename) and filename.startswith(valid_prefixes):
                chunk_path = os.path.join(self.chunks_dir, filename)
                try:
                    with open(chunk_path, encoding="utf-8") as f:
                        chunk = json.load(f)
                    chunk["source_filename"] = filename
                    chunks.append(chunk)
                except Exception as e:
                    print(f"[FileRepository] 加载块失败 {chunk_path}: {e}")

        chunks.sort(key=lambda x: x.get("chunk_index", 0))
        return chunks

    def get_chunk_by_id(self, file_title: str, chunk_index: int) -> dict[str, Any] | None:
        """按索引获取单个块

        Args:
            file_title: 文件标题
            chunk_index: 块索引（从0开始）

        Returns:
            块数据字典，不存在返回None
        """
        normalized_title = file_title.replace(" ", "_").lower()
        candidate_filenames = [
            f"{file_title}_chunk_{chunk_index:03d}.json",
            f"{normalized_title}_chunk_{chunk_index:03d}.json",
        ]

        for chunk_filename in dict.fromkeys(candidate_filenames):
            chunk_path = os.path.join(self.chunks_dir, chunk_filename)
            if not os.path.exists(chunk_path):
                continue
            try:
                with open(chunk_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[FileRepository] 加载块失败 {chunk_path}: {e}")
        return None

    def load_aggregated_data(self, file_title: str) -> dict[str, Any] | None:
        """加载文件的完整聚合数据（优先使用块文件，回退到原始文件）

        Args:
            file_title: 文件标题

        Returns:
            聚合后的完整数据
        """
        chunks = self.get_all_chunks(file_title)

        if chunks:
            first_chunk = chunks[0]
            data_container = first_chunk.get("data")

            if isinstance(data_container, list):
                result = []
                for chunk in chunks:
                    chunk_data = chunk.get("data", [])
                    if isinstance(chunk_data, list):
                        result.extend(chunk_data)
                return result
            elif isinstance(data_container, dict):
                result = {}
                for chunk in chunks:
                    chunk_data = chunk.get("data", {})
                    if isinstance(chunk_data, dict):
                        result.update(chunk_data)
                return result

        original_path = os.path.join(self.original_dir, f"{file_title}.json")
        if os.path.exists(original_path):
            try:
                with open(original_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[FileRepository] 加载原始文件失败 {original_path}: {e}")

        return None

    def get_existing_chunks(self, file_title: str) -> list[str]:
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
                if fname.startswith(valid_prefixes) and "_chunk_" in fname:
                    existing.append(os.path.join(self.chunks_dir, fname))
        return existing

    def clear_cache(self):
        """清除文件缓存"""
        self._file_cache.clear()

    def get_file_cache_size(self) -> int:
        """获取文件缓存大小"""
        return len(self._file_cache)
