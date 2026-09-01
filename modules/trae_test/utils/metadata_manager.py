"""
知识库元数据管理模块 v3.0
用于管理文件注册、标签分类等元数据信息
"""

import datetime
import json
import os
import tempfile
from typing import Any

from .hash_utils import compute_file_hash
from .path_utils import PathManager


class MetadataManager:
    """知识库元数据管理器"""

    VERSION = "3.0"
    REGISTRY_FILE = "file_registry.json"

    # 分类标签映射（从旧的分类目录中提取）
    CLASSIFICATION_MAPPING = {
        "销售模块": ["销售模块", "销售订单", "销售订单", "销售"],
        "采购模块": ["采购模块", "采购订单", "采购"],
        "产品模块": ["产品模块", "产品"],
        "财务模块": ["财务模块", "财务", "佣金", "账单"],
        "物流模块": ["物流模块", "物流"],
        "WMS仓储": ["WMS仓储模块", "WMS"],
        "WMS_PDA": ["WMS_PDA模块", "WMS_PDA"],
        "系统模块": ["系统模块", "系统"],
        "维护模块": ["维护模块", "维护"],
        "Dashboard": ["Dashboard模块", "Dashboard"],
        "业务规则": ["需求清单", "全链路业务流程", "业务规则"],
        "测试规范": ["已学习测试用例", "测试用例模板", "缺陷报告规范"],
        "自动化规范": ["技术栈与工程结构", "脚本编写规范", "DOM与Playwright"],
        "导航规范": ["ERP菜单导航与路由"],
        "性能优化": ["销售订单列表性能优化规范"],
        "接口规范": ["销售订单搜索接口规范"],
        "字段规范": ["销售订单字段规范", "销售订单导出列配置"],
        "媒体资源": ["销售订单SKU图片显示规则"],
        "线上问题": ["线上问题分析", "线上问题知识库"],
        "数据核对": ["数据核对"],
        "功能规格": ["功能规格"],
        "技术规范": ["数据库结构", "数据库"],
    }

    def __init__(self, kb_base_dir: str | None = None):
        if kb_base_dir is None:
            self.kb_base_dir = PathManager.get_kb_base_dir()
        else:
            self.kb_base_dir = kb_base_dir

        self.metadata_dir = os.path.join(self.kb_base_dir, "metadata")
        self.registry_path = os.path.join(self.metadata_dir, self.REGISTRY_FILE)
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        if not os.path.exists(self.metadata_dir):
            os.makedirs(self.metadata_dir, exist_ok=True)

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """计算文件的SHA256哈希值"""
        return compute_file_hash(file_path)

    @staticmethod
    def _extract_file_tags(title: str) -> list[str]:
        """从文件标题自动提取标签"""
        tags = []

        for classification, keywords in MetadataManager.CLASSIFICATION_MAPPING.items():
            for keyword in keywords:
                if keyword in title:
                    tags.append(classification)
                    tags.append(keyword)
                    break

        return list(set(tags))

    @staticmethod
    def _extract_declared_tags(file_path: str) -> list[str]:
        """Read optional top-level tags from a JSON knowledge file."""
        if not file_path.lower().endswith(".json"):
            return []

        try:
            with open(file_path, encoding="utf-8") as f:
                content = json.load(f)
        except Exception:
            return []

        if not isinstance(content, dict):
            return []

        tags = content.get("tags", [])
        if not isinstance(tags, list):
            return []

        return [str(tag).strip() for tag in tags if str(tag).strip()]

    @staticmethod
    def _classify_file(title: str) -> str:
        """根据标题自动分类文件"""
        for classification, keywords in MetadataManager.CLASSIFICATION_MAPPING.items():
            for keyword in keywords:
                if keyword in title:
                    return classification
        return "其他"

    @staticmethod
    def _sync_reverse_tags(registry: dict[str, Any]) -> None:
        """Rebuild the reverse tag index from registry['files'][*]['tags']."""
        tag_index: dict[str, list[str]] = {}
        for file_id, file_info in registry.get("files", {}).items():
            for tag in file_info.get("tags", []):
                if not tag:
                    continue
                tag_index.setdefault(tag, [])
                if file_id not in tag_index[tag]:
                    tag_index[tag].append(file_id)
        registry["tags"] = tag_index

    def _count_actual_chunks(self, file_id: str) -> int:
        """统计指定文件的实际分块数"""
        chunks_dir = os.path.join(self.kb_base_dir, "data", "chunks")
        if not os.path.exists(chunks_dir):
            return 0
        count = 0
        prefix = file_id + "_"
        for fname in os.listdir(chunks_dir):
            if fname.startswith(prefix) and "_chunk_" in fname and fname.endswith(".json"):
                count += 1
        return count

    def scan_and_register_all(self, original_dir: str | None = None, allow_shrink: bool = False) -> dict[str, Any]:
        """扫描并注册所有原始文件"""
        if original_dir is None:
            original_dir = os.path.join(self.kb_base_dir, "data", "original")

        result = {"success": True, "registered_files": 0, "files": [], "error": ""}

        if not os.path.isdir(original_dir):
            result.update(success=False, error=f"知识库原始目录不存在: {original_dir}")
            return result

        previous = self.load_registry() or {}
        previous_count = len(previous.get("files", {}))

        registry = {
            "version": self.VERSION,
            "generated_at": datetime.datetime.now().isoformat(),
            "files": {},
            "tags": {},
        }

        for filename in os.listdir(original_dir):
            if filename.endswith(".json") or filename.endswith(".md"):
                file_path = os.path.join(original_dir, filename)

                title = os.path.splitext(filename)[0]
                file_id = title.replace(" ", "_").lower()

                stat = os.stat(file_path)

                tags = list(set(self._extract_file_tags(title) + self._extract_declared_tags(file_path)))
                classification = self._classify_file(title)
                chunk_count = self._count_actual_chunks(file_id)

                file_info = {
                    "file_id": file_id,
                    "title": title,
                    "original_path": f"data/original/{filename}",
                    "chunks_path": f"data/chunks/{file_id}/",
                    "tags": tags,
                    "classification": classification,
                    "hash": self._compute_file_hash(file_path),
                    "created_at": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "last_modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "chunk_count": chunk_count,
                    "total_size": stat.st_size,
                }

                registry["files"][file_id] = file_info

                result["files"].append(title)
                result["registered_files"] += 1

        if previous_count and result["registered_files"] < previous_count and not allow_shrink:
            result.update(
                success=False,
                error=(
                    f"拒绝覆盖注册表：文件数量从 {previous_count} 降至 "
                    f"{result['registered_files']}；如确认删除，请显式传入 allow_shrink=True"
                ),
            )
            return result

        self._sync_reverse_tags(registry)

        fd, temp_path = tempfile.mkstemp(prefix="file_registry_", suffix=".tmp", dir=self.metadata_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.registry_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        return result

    def load_registry(self) -> dict[str, Any] | None:
        """加载文件注册表"""
        if os.path.exists(self.registry_path):
            with open(self.registry_path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def get_files_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """根据标签查询文件列表"""
        registry = self.load_registry()
        if not registry or tag not in registry["tags"]:
            return []

        return [registry["files"][file_id] for file_id in registry["tags"][tag]]

    def get_file_by_id(self, file_id: str) -> dict[str, Any] | None:
        """根据文件ID获取文件信息"""
        registry = self.load_registry()
        if not registry or file_id not in registry["files"]:
            return None
        return registry["files"][file_id]

    def update_file(self, file_id: str, updates: dict[str, Any]) -> bool:
        """更新文件信息"""
        registry = self.load_registry()
        if not registry or file_id not in registry["files"]:
            return False

        registry["files"][file_id].update(updates)
        self._sync_reverse_tags(registry)

        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

        return True


if __name__ == "__main__":
    print("=" * 60)
    print("知识库元数据管理工具 v3.0")
    print("=" * 60)

    manager = MetadataManager()
    print("\n开始扫描并注册文件...")

    result = manager.scan_and_register_all()

    if result["success"]:
        print(f"\n✅ 成功注册 {result['registered_files']} 个文件")
        print("📋 注册的文件：")
        for filename in result["files"]:
            print(f"  - {filename}")

        print(f"\n📁 元数据已保存至: {manager.registry_path}")

        print("\n📊 注册信息预览：")
        registry = manager.load_registry()
        print(f"  版本: {registry['version']}")
        print(f"  生成时间: {registry['generated_at']}")
        print(f"  文件数量: {len(registry['files'])}")
        print(f"  标签数量: {len(registry['tags'])}")
    else:
        print(f"\n❌ 注册失败: {result.get('error', '未知错误')}")
