"""知识库数据访问层 - 元数据仓储"""

import json
import os
from typing import Any

from .path_utils import PathManager


class MetadataRepository:
    """元数据仓储 - 提供文件注册表管理和标签搜索功能"""

    def __init__(self, kb_base_dir: str = None):
        self.kb_base_dir = kb_base_dir or PathManager.get_kb_base_dir()
        self.metadata_dir = PathManager.get_metadata_dir()
        self.registry_path = os.path.join(self.metadata_dir, "file_registry.json")

        self._registry = None
        self._rule_file_index = []
        self._rules_loaded = False

    def load_registry(self):
        """加载文件注册表 metadata/file_registry.json"""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, encoding="utf-8") as f:
                    self._registry = json.load(f)
            except Exception as e:
                print(f"[MetadataRepository] 加载文件注册表失败: {e}")
                self._registry = {"files": {}, "tags": {}}
        else:
            print(f"[MetadataRepository] 文件注册表不存在: {self.registry_path}")
            self._registry = {"files": {}, "tags": {}}

    def get_registry(self) -> dict[str, Any] | None:
        """获取注册表数据"""
        if self._registry is None:
            self.load_registry()
        return self._registry

    def get_file_by_id(self, file_id: str) -> dict[str, Any] | None:
        """根据文件ID获取文件信息"""
        if not self.get_registry():
            return None
        return self._registry.get("files", {}).get(file_id)

    def get_files_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """根据标签获取文件列表"""
        if not self.get_registry():
            return []

        if tag is None:
            return []

        tag = tag.strip()
        files_list = []

        if tag in self._registry.get("tags", {}):
            file_ids = self._registry["tags"].get(tag, [])
            for file_id in file_ids:
                file_info = self.get_file_by_id(file_id)
                if file_info:
                    files_list.append(file_info)

        if not files_list:
            for existing_tag, file_ids in self._registry.get("tags", {}).items():
                if tag in existing_tag or existing_tag in tag:
                    for file_id in file_ids:
                        file_info = self.get_file_by_id(file_id)
                        if file_info and file_info not in files_list:
                            files_list.append(file_info)

        return files_list

    def search_by_tags(self, *tags: str) -> list[dict[str, Any]]:
        """按多个标签检索文件"""
        if not tags:
            return []

        results = []
        for tag in tags:
            files = self.get_files_by_tag(tag)
            for file_info in files:
                if file_info not in results:
                    results.append(file_info)

        return results

    def ensure_rules_loaded(self):
        """建立规则文件索引（仅扫描元数据，不加载文件内容）"""
        if self._rules_loaded:
            return
        self._rules_loaded = True

        if not self.get_registry():
            return

        rule_tags = [
            "业务规则",
            "销售模块",
            "采购模块",
            "产品模块",
            "财务模块",
            "物流模块",
            "系统模块",
            "WMS仓储",
            "Dashboard",
        ]

        seen_file_ids = set()

        for tag in rule_tags:
            if tag not in self._registry.get("tags", {}):
                continue
            for file_id in self._registry["tags"].get(tag, []):
                if file_id in seen_file_ids:
                    continue
                seen_file_ids.add(file_id)

                file_info = self.get_file_by_id(file_id)
                if not file_info:
                    continue

                original_path = file_info.get("original_path", "")
                if not original_path or not original_path.lower().endswith(".json"):
                    continue

                self._rule_file_index.append(
                    {
                        "file_id": file_id,
                        "title": file_info.get("title", ""),
                        "classification": file_info.get("classification", ""),
                        "original_path": original_path,
                    }
                )

    def get_rule_file_index(self) -> list[dict[str, Any]]:
        """获取规则文件索引"""
        self.ensure_rules_loaded()
        return self._rule_file_index

    def list_available_files(self) -> list[str]:
        """列出所有可用的文件"""
        if not self.get_registry():
            return []
        return list(self._registry.get("files", {}).keys())

    def get_registry_stats(self) -> dict[str, int]:
        """获取注册表统计信息"""
        files_count = len(self._registry.get("files", {})) if self._registry else 0
        tags_count = len(self._registry.get("tags", {})) if self._registry else 0

        return {"total_files": files_count, "total_tags": tags_count}

    def clear_rule_index(self):
        """清除规则文件索引"""
        self._rule_file_index.clear()
        self._rules_loaded = False
