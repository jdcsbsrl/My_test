"""索引构建器 v3.0 - 为知识库生成文件级索引和全局索引"""

import gzip
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from collections import Counter
from typing import Any

from .path_utils import PathManager


class IndexBuilderV3:
    """索引构建器 v3.0 - 支持大文件处理和进度跟踪"""

    def __init__(self):
        """初始化索引构建器"""
        # v3.0 架构目录结构
        self.knowledge_base_dir = PathManager.get_kb_base_dir()
        self.data_dir = PathManager.get_data_dir()
        self.original_dir = PathManager.get_original_dir()
        self.chunks_dir = PathManager.get_chunks_dir()
        self.index_dir = PathManager.get_index_dir()
        self.metadata_dir = PathManager.get_metadata_dir()

        self.files_index_dir = os.path.join(self.index_dir, "files")
        self.global_index_dir = os.path.join(self.index_dir, "global")
        self.inverted_index_dir = os.path.join(self.index_dir, "inverted")

        # 文件注册表路径
        self.registry_path = os.path.join(self.metadata_dir, "file_registry.json")
        self._registry = None

        # 进度跟踪
        self._progress = {
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "start_time": 0,
            "current_file": "",
        }

        # 业务领域词表
        self.domain_vocabulary = {
            "销售",
            "采购",
            "订单",
            "商品",
            "SKU",
            "库存",
            "物流",
            "财务",
            "客户",
            "供应商",
            "价格",
            "报价",
            "折扣",
            "退款",
            "发货",
            "入库",
            "出库",
            "盘点",
            "账单",
            "发票",
            "凭证",
            "审批",
            "规则",
            "约束",
            "验证",
            "配置",
            "参数",
            "接口",
            "API",
            "模块",
            "页面",
            "功能",
            "流程",
            "状态",
            "操作",
            "查询",
        }

        # 高频停用词
        self.stop_words = {
            "的",
            "了",
            "和",
            "是",
            "就",
            "都",
            "而",
            "及",
            "与",
            "着",
            "或",
            "一个",
            "没有",
            "我们",
            "你们",
            "他们",
            "它们",
            "这",
            "那",
            "这些",
            "那些",
            "什么",
            "怎么",
            "如何",
            "因为",
            "所以",
            "但是",
            "然而",
            "虽然",
            "如果",
            "可以",
            "应该",
            "必须",
            "需要",
            "已经",
            "正在",
            "将要",
            "曾经",
            "能够",
            "会",
            "可能",
            "要",
            "得",
            "可",
            "现在",
            "今天",
            "明天",
            "昨天",
            "时间",
            "时候",
            "地方",
            "这里",
            "那里",
            "这样",
            "那样",
            "这么",
            "那么",
            "非常",
            "特别",
            "很",
            "太",
            "也",
            "还",
            "更",
            "最",
            "才",
            "又",
            "再",
            "已",
            "曾",
            "将",
            "应",
            "该",
            "过",
        }

        # 确保目录存在
        self._ensure_directories()

    @staticmethod
    def _atomic_write_json(path: str, payload: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="index_", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _ensure_directories(self):
        """确保必要的目录存在"""
        PathManager.ensure_kb_directories()

        dirs_to_create = [self.files_index_dir, self.global_index_dir, self.inverted_index_dir]

        for dir_path in dirs_to_create:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

    def _load_registry(self):
        """加载文件注册表"""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, encoding="utf-8") as f:
                    self._registry = json.load(f)
            except Exception as e:
                print(f"[IndexBuilderV3] 加载文件注册表失败: {e}")
                self._registry = None
        else:
            self._registry = None

    def _get_file_info(self, file_id: str) -> dict[str, Any] | None:
        """获取文件信息"""
        if not self._registry:
            return None
        return self._registry.get("files", {}).get(file_id)

    def _extract_keywords(self, content: Any, max_keywords: int = 15) -> list[str]:
        """从内容中提取关键词

        Args:
            content: 任意类型的内容
            max_keywords: 最大关键词数量

        Returns:
            关键词列表
        """
        if content is None:
            return []

        content_str = json.dumps(content, ensure_ascii=False)

        # 提取中文词语（2-4字符）和英文单词
        chinese_words = re.findall(r"[\u4e00-\u9fa5]{2,4}", content_str)
        english_words = re.findall(r"[a-zA-Z]{3,}", content_str)

        all_words = chinese_words + english_words

        # 过滤停用词
        stop_words = {
            "的",
            "是",
            "在",
            "有",
            "和",
            "了",
            "我",
            "你",
            "他",
            "她",
            "它",
            "这",
            "那",
            "这些",
            "那些",
            "什么",
            "怎么",
            "为什么",
            "因为",
            "所以",
            "但是",
            "而且",
            "如果",
            "可以",
            "可能",
            "应该",
            "需要",
            "必须",
            "一个",
            "一些",
            "所有",
            "每个",
            "任何",
            "没有",
            "不是",
            "不要",
            "我们",
            "你们",
            "他们",
            "它们",
            "自己",
            "之间",
            "之后",
            "之前",
            "现在",
            "今天",
            "明天",
            "昨天",
            "时间",
            "时候",
            "地方",
            "这里",
            "那里",
            "这样",
            "那样",
            "这么",
            "那么",
            "非常",
            "特别",
            "很",
            "太",
            "也",
            "都",
            "还",
            "更",
            "最",
            "就",
            "才",
            "又",
            "再",
            "已",
            "曾",
            "将",
            "会",
            "能",
            "可",
            "要",
            "应",
            "该",
            "得",
            "着",
            "过",
        }

        filtered = [word for word in all_words if word not in stop_words]

        # 统计词频并排序
        word_counts = Counter(filtered)

        # 加权评分（长词权重更高，含数字降低权重）
        def calculate_weight(word: str, count: int) -> float:
            base_weight = count
            # 长度奖励
            if len(word) >= 3:
                base_weight *= 1.5
            # 数字惩罚
            if any(c.isdigit() for c in word):
                base_weight *= 0.5
            return base_weight

        weighted_words = [(word, calculate_weight(word, count)) for word, count in word_counts.items()]
        weighted_words.sort(key=lambda x: -x[1])

        return [word for word, weight in weighted_words[:max_keywords]]

    def _generate_summary(self, content: Any, max_length: int = 200) -> str:
        """生成内容摘要

        Args:
            content: 任意类型的内容
            max_length: 摘要最大长度

        Returns:
            摘要字符串
        """
        if content is None:
            return ""

        content_str = json.dumps(content, ensure_ascii=False, separators=(",", ":"))

        # 移除特殊字符，保留主要内容
        clean_str = re.sub(r'[{}[\]":,\\]', " ", content_str)
        clean_str = re.sub(r"\s+", " ", clean_str).strip()

        if len(clean_str) <= max_length:
            return clean_str

        return clean_str[:max_length] + "..."

    def _extract_keywords_from_text(self, text: str, max_keywords: int = 10) -> list[str]:
        """从文本中提取关键词（用于Markdown文件）

        Args:
            text: 文本内容
            max_keywords: 最大关键词数量

        Returns:
            关键词列表
        """
        import re
        from collections import Counter

        # 移除Markdown格式
        clean_text = re.sub(r"[#*`>\-\[\]()]+", " ", text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        # 提取中文词和英文词
        chinese_words = re.findall(r"[\u4e00-\u9fa5]{2,}", clean_text)
        english_words = re.findall(r"[a-zA-Z]{3,}", clean_text)

        all_words = chinese_words + english_words

        stop_words = {
            "的",
            "了",
            "和",
            "是",
            "就",
            "都",
            "而",
            "及",
            "与",
            "着",
            "或",
            "一个",
            "没有",
            "我们",
            "你们",
            "他们",
            "它们",
            "这",
            "那",
            "这些",
            "那些",
            "什么",
            "怎么",
            "如何",
            "因为",
            "所以",
            "但是",
            "然而",
            "虽然",
            "如果",
            "可以",
            "应该",
            "必须",
            "需要",
            "已经",
            "正在",
            "将要",
            "曾经",
            "能够",
            "会",
            "可能",
            "要",
            "得",
            "可",
            "现在",
            "今天",
            "明天",
            "昨天",
            "时间",
            "时候",
            "地方",
            "这里",
            "那里",
            "这样",
            "那样",
            "这么",
            "那么",
            "非常",
            "特别",
            "很",
            "太",
            "也",
            "还",
            "更",
            "最",
            "才",
            "又",
            "再",
            "已",
            "曾",
            "将",
            "应",
            "该",
            "过",
        }

        filtered = [word for word in all_words if word not in stop_words]

        word_counts = Counter(filtered)

        def calculate_weight(word: str, count: int) -> float:
            base_weight = count
            if len(word) >= 3:
                base_weight *= 1.5
            if any(c.isdigit() for c in word):
                base_weight *= 0.5
            return base_weight

        weighted_words = [(word, calculate_weight(word, count)) for word, count in word_counts.items()]
        weighted_words.sort(key=lambda x: -x[1])

        return [word for word, weight in weighted_words[:max_keywords]]

    def _generate_summary_from_text(self, text: str, max_length: int = 200) -> str:
        """从文本生成摘要（用于Markdown文件）

        Args:
            text: 文本内容
            max_length: 摘要最大长度

        Returns:
            摘要字符串
        """
        if not text:
            return ""

        import re

        clean_text = re.sub(r"[#*`>\-\[\]()]+", " ", text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        if len(clean_text) <= max_length:
            return clean_text

        return clean_text[:max_length] + "..."

    def _process_file(self, filename: str) -> dict[str, Any]:
        """处理单个文件，生成文件级索引

        Args:
            filename: 文件名

        Returns:
            处理结果
        """
        result = {"success": False, "file_id": "", "filename": filename, "error": ""}

        try:
            file_path = os.path.join(self.original_dir, filename)

            # 构建文件ID
            file_id = os.path.splitext(filename)[0].replace(" ", "_").lower()
            result["file_id"] = file_id

            # 获取文件信息（从注册表）
            file_info = self._get_file_info(file_id)
            tags = file_info.get("tags", []) if file_info else []

            # 获取文件统计信息
            stat = os.stat(file_path)

            # 根据文件扩展名处理
            if filename.lower().endswith(".json"):
                # JSON 文件处理
                with open(file_path, encoding="utf-8") as f:
                    content = json.load(f)

                # 提取关键词
                keywords = self._extract_keywords(content)

                # 生成摘要
                summary = self._generate_summary(content)

            elif filename.lower().endswith(".md"):
                # Markdown 文件处理
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # 提取关键词（从Markdown文本中）
                keywords = self._extract_keywords_from_text(content)

                # 生成摘要（直接使用开头部分）
                summary = self._generate_summary_from_text(content)

            else:
                # 未知文件类型
                result["error"] = f"不支持的文件类型: {filename}"
                return result

            # 构建文件级索引
            file_index = {
                "version": "3.0",
                "file_id": file_id,
                "filename": filename,
                "title": file_info.get("title", file_id) if file_info else file_id,
                "tags": tags,
                "keywords": keywords,
                "summary": summary,
                "file_size": stat.st_size,
                "created_at": stat.st_ctime,
                "last_modified": stat.st_mtime,
                "classification": file_info.get("classification", "") if file_info else "",
                "hash": file_info.get("hash", "") if file_info else "",
            }

            # 保存文件级索引
            index_path = os.path.join(self.files_index_dir, f"{file_id}_index.json")
            self._atomic_write_json(index_path, file_index)

            result["success"] = True
            result["index_path"] = index_path

        except Exception as e:
            result["error"] = str(e)

        return result

    def build_file_indexes(self, file_filter: str | None = None) -> dict[str, Any]:
        """构建文件级索引

        Args:
            file_filter: 文件过滤模式（可选）

        Returns:
            构建结果
        """
        print("[IndexBuilderV3] 开始构建文件级索引...")

        self._load_registry()

        result = {
            "success": True,
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "results": [],
            "error": "",
        }

        try:
            if not os.path.exists(self.original_dir):
                result["error"] = "原始文件目录不存在"
                result["success"] = False
                return result

            # 获取文件列表
            all_files = [f for f in os.listdir(self.original_dir) if f.endswith(".json") or f.endswith(".md")]

            if file_filter:
                all_files = [f for f in all_files if file_filter in f]

            total_files = len(all_files)
            result["total_files"] = total_files
            self._progress["total_files"] = total_files
            self._progress["processed_files"] = 0
            self._progress["failed_files"] = 0

            print(f"[IndexBuilderV3] 发现 {total_files} 个文件需要处理")

            for i, filename in enumerate(all_files, 1):
                self._progress["current_file"] = filename

                print(f"[IndexBuilderV3] 处理 {i}/{total_files}: {filename}")

                process_result = self._process_file(filename)
                result["results"].append(process_result)

                if process_result["success"]:
                    self._progress["processed_files"] += 1
                    result["processed_files"] += 1
                else:
                    self._progress["failed_files"] += 1
                    result["failed_files"] += 1
                    print(f"[IndexBuilderV3] 处理失败 {filename}: {process_result['error']}")

            print(f"[IndexBuilderV3] 文件级索引构建完成: {result['processed_files']}/{total_files}")

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)

        return result

    def build_global_index(self) -> dict[str, Any]:
        """构建全局索引

        Returns:
            构建结果
        """
        print("[IndexBuilderV3] 开始构建全局索引...")

        result = {"success": False, "indexed_files": 0, "error": ""}

        try:
            if not os.path.exists(self.files_index_dir):
                result["error"] = "文件级索引目录不存在"
                return result

            self._load_registry()
            registry_files = (self._registry or {}).get("files")
            allowed_ids = set(registry_files) if registry_files else None
            # Only current registered files may enter the global index.
            index_files = [f for f in os.listdir(self.files_index_dir) if f.endswith("_index.json")]
            orphan_indexes = []
            if allowed_ids is not None:
                orphan_indexes = [f for f in index_files if f.removesuffix("_index.json") not in allowed_ids]
                index_files = [f for f in index_files if f not in orphan_indexes]

            # 聚合索引信息
            global_index = {
                "version": "3.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "file_count": len(index_files),
                "orphan_indexes": orphan_indexes,
                "files": [],
                "tags": {},
                "classifications": {},
            }

            for index_file in index_files:
                index_path = os.path.join(self.files_index_dir, index_file)
                with open(index_path, encoding="utf-8") as f:
                    file_index = json.load(f)

                # 添加文件信息
                global_index["files"].append(
                    {
                        "file_id": file_index["file_id"],
                        "filename": file_index["filename"],
                        "title": file_index["title"],
                        "classification": file_index["classification"],
                        "tags": file_index["tags"],
                        "summary": file_index["summary"],
                        "file_size": file_index["file_size"],
                        "last_modified": file_index["last_modified"],
                    }
                )

                # 聚合标签
                for tag in file_index["tags"]:
                    if tag not in global_index["tags"]:
                        global_index["tags"][tag] = []
                    global_index["tags"][tag].append(file_index["file_id"])

                # 聚合分类
                classification = file_index["classification"]
                if classification and classification not in global_index["classifications"]:
                    global_index["classifications"][classification] = []
                if classification:
                    global_index["classifications"][classification].append(file_index["file_id"])

            # 保存全局索引
            global_index_path = os.path.join(self.global_index_dir, "global_index.json")
            self._atomic_write_json(global_index_path, global_index)

            result["success"] = True
            result["indexed_files"] = len(index_files)
            result["index_path"] = global_index_path

            print(f"[IndexBuilderV3] 全局索引构建完成，共索引 {len(index_files)} 个文件")

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)

        return result

    def build_all_indexes(self, file_filter: str | None = None) -> dict[str, Any]:
        """构建所有索引（文件级索引 + 全局索引）

        Args:
            file_filter: 文件过滤模式（可选）

        Returns:
            构建结果
        """
        print("[IndexBuilderV3] 开始构建所有索引...")

        result = {"file_indexes": {}, "global_index": {}, "inverted_index": {}, "overall_success": False}

        # 构建文件级索引
        file_result = self.build_file_indexes(file_filter)
        result["file_indexes"] = file_result

        if file_result["success"]:
            # 构建全局索引
            global_result = self.build_global_index()
            result["global_index"] = global_result
            if global_result["success"]:
                result["inverted_index"] = self.build_inverted_index()
            result["overall_success"] = global_result["success"] and result["inverted_index"].get("success", False)

        return result

    def get_progress(self) -> dict[str, Any]:
        """获取当前处理进度

        Returns:
            进度信息
        """
        return self._progress

    def list_existing_indexes(self) -> list[str]:
        """列出已存在的文件级索引

        Returns:
            索引文件名列表
        """
        if not os.path.exists(self.files_index_dir):
            return []

        return [f for f in os.listdir(self.files_index_dir) if f.endswith("_index.json")]

    def clear_all_indexes(self) -> dict[str, Any]:
        """清除所有索引

        Returns:
            清除结果
        """
        result = {"success": True, "deleted_files": 0, "error": ""}

        try:
            # 删除文件级索引
            if os.path.exists(self.files_index_dir):
                for filename in os.listdir(self.files_index_dir):
                    if filename.endswith("_index.json"):
                        os.remove(os.path.join(self.files_index_dir, filename))
                        result["deleted_files"] += 1

            # 删除全局索引
            global_index_path = os.path.join(self.global_index_dir, "global_index.json")
            if os.path.exists(global_index_path):
                os.remove(global_index_path)
                result["deleted_files"] += 1

            print(f"[IndexBuilderV3] 已清除 {result['deleted_files']} 个索引文件")

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)

        return result

    def prune_orphan_file_indexes(self, confirm: bool = False) -> dict[str, Any]:
        """Report or explicitly remove file indexes absent from the registry."""
        self._load_registry()
        registered = set((self._registry or {}).get("files", {}))
        existing = [f for f in os.listdir(self.files_index_dir) if f.endswith("_index.json")]
        orphaned = [f for f in existing if f.removesuffix("_index.json") not in registered]
        result = {"success": True, "orphaned": orphaned, "removed": []}
        if confirm:
            for filename in orphaned:
                os.remove(os.path.join(self.files_index_dir, filename))
                result["removed"].append(filename)
        return result

    def build_inverted_index(self) -> dict[str, Any]:
        """构建倒排索引

        Returns:
            构建结果
        """
        print("[IndexBuilderV3] 开始构建倒排索引...")

        result = {"success": False, "total_chunks": 0, "indexed_chunks": 0, "total_keywords": 0, "error": ""}

        try:
            if not os.path.exists(self.chunks_dir):
                result["error"] = "chunk目录不存在"
                return result

            # 遍历所有chunk文件
            chunk_files = self._traverse_chunk_files()
            result["total_chunks"] = len(chunk_files)

            if not chunk_files:
                print("[IndexBuilderV3] 未发现chunk文件")
                result["success"] = True
                return result

            # 构建倒排索引
            inverted_index = self._construct_inverted_index(chunk_files)
            failed_chunks = getattr(self, "_last_inverted_failures", [])
            result["failed_chunks"] = failed_chunks
            if failed_chunks:
                result["error"] = f"{len(failed_chunks)} 个chunk读取失败"
                return result
            result["total_keywords"] = len(inverted_index)
            if not inverted_index:
                result["error"] = "chunk未提取到任何关键词"
                return result

            # 优化索引
            self._optimize_index(inverted_index)

            # 保存索引（gzip压缩）
            self._save_inverted_index(inverted_index)

            result["success"] = True
            result["indexed_chunks"] = len(chunk_files)

            print(
                f"[IndexBuilderV3] 倒排索引构建完成，共索引 {len(chunk_files)} 个chunk，{len(inverted_index)} 个关键词"
            )

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            print(f"[IndexBuilderV3] 倒排索引构建失败: {e}")

        return result

    def _traverse_chunk_files(self) -> list[str]:
        """遍历data/chunks/目录下所有切片文件

        Returns:
            chunk文件路径列表
        """
        chunk_files = []

        if os.path.exists(self.chunks_dir):
            for root, _, filenames in os.walk(self.chunks_dir):
                for filename in filenames:
                    if "_chunk_" in filename and filename.endswith(".json"):
                        chunk_files.append(os.path.join(root, filename))

        return chunk_files

    def _extract_keywords(self, chunk_content: dict[str, Any]) -> dict[str, float]:
        """提取chunk的关键词及其权重

        Args:
            chunk_content: chunk内容

        Returns:
            关键词到权重的映射
        """
        keywords = {}

        # 收集所有文本内容
        text_parts = []

        # 从metadata提取
        metadata = chunk_content.get("metadata", {})
        text_parts.append(str(metadata.get("module", "")))
        text_parts.append(str(metadata.get("rule_id", "")))
        text_parts.append(str(metadata.get("source_file", "")))

        # 从content提取
        content = chunk_content.get("content", {})
        text_parts.append(str(content.get("rule_name", "")))
        text_parts.append(str(content.get("rule_description", "")))
        text_parts.append(str(content.get("rule_condition", "")))
        text_parts.append(str(content.get("rule_action", "")))
        text_parts.append(str(content.get("rule_source", "")))

        # 处理original_rule
        original_rule = content.get("original_rule", "")
        if isinstance(original_rule, dict):
            for val in original_rule.values():
                text_parts.append(str(val))
        else:
            text_parts.append(str(original_rule))

        # 合并所有文本
        full_text = " ".join(text_parts)
        if not full_text.strip():
            full_text = json.dumps(chunk_content, ensure_ascii=False)

        # 提取中文词和英文词
        chinese_words = re.findall(r"[\u4e00-\u9fa5]{2,}", full_text)
        english_words = re.findall(r"[a-zA-Z]{2,}", full_text.upper())

        all_words = chinese_words + english_words

        # 统计词频
        word_counts = Counter(all_words)

        # 计算权重
        total_words = sum(word_counts.values()) if word_counts else 1

        for word, count in word_counts.items():
            # 跳过停用词
            if word.lower() in self.stop_words or word in self.stop_words:
                continue

            # 基础权重（词频）
            weight = count / total_words

            # 领域词表加成
            if word in self.domain_vocabulary or word.lower() in self.domain_vocabulary:
                weight *= 2.0

            # 长度加成（较长的词更重要）
            if len(word) >= 3:
                weight *= 1.5

            # 数字惩罚
            if any(c.isdigit() for c in word):
                weight *= 0.5

            keywords[word] = weight

        return keywords

    def _construct_inverted_index(self, chunk_files: list[str]) -> dict[str, list[dict[str, Any]]]:
        """构建倒排索引数据结构

        Args:
            chunk_files: chunk文件路径列表

        Returns:
            倒排索引：{关键词: [{chunk_id, weight, field}, ...]}
        """
        inverted_index = {}
        self._last_inverted_failures = []

        for chunk_path in chunk_files:
            try:
                with open(chunk_path, encoding="utf-8") as f:
                    chunk = json.load(f)

                chunk_id = chunk.get("chunk_id") or os.path.splitext(os.path.basename(chunk_path))[0]
                if not chunk_id:
                    continue

                # 提取关键词
                keywords = self._extract_keywords(chunk)

                # 添加到倒排索引
                for keyword, weight in keywords.items():
                    if keyword not in inverted_index:
                        inverted_index[keyword] = []

                    inverted_index[keyword].append(
                        {
                            "chunk_id": chunk_id,
                            "weight": weight,
                            "field": "content",
                            "source_file": os.path.basename(chunk_path),
                        }
                    )

            except Exception as e:
                print(f"[IndexBuilderV3] 处理chunk文件失败 {chunk_path}: {e}")
                self._last_inverted_failures.append(chunk_path)

        return inverted_index

    def _optimize_index(self, inverted_index: dict[str, list[dict[str, Any]]]):
        """优化索引

        Args:
            inverted_index: 倒排索引
        """
        # 对每个关键词的条目按权重排序
        for keyword, entries in inverted_index.items():
            entries.sort(key=lambda x: -x["weight"])

            # 限制每个关键词最多保留50个条目
            if len(entries) > 50:
                inverted_index[keyword] = entries[:50]

        # 计算全局权重归一化
        max_weight = 1.0
        for entries in inverted_index.values():
            for entry in entries:
                if entry["weight"] > max_weight:
                    max_weight = entry["weight"]

        if max_weight > 0:
            for entries in inverted_index.values():
                for entry in entries:
                    entry["weight"] = entry["weight"] / max_weight

    def _save_inverted_index(self, inverted_index: dict[str, list[dict[str, Any]]]):
        """保存倒排索引（gzip压缩）

        Args:
            inverted_index: 倒排索引
        """
        index_data = {
            "version": "3.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_keywords": len(inverted_index),
            "index": inverted_index,
        }

        index_path = os.path.join(self.inverted_index_dir, "inverted_index.json")
        compressed_path = os.path.join(self.inverted_index_dir, "inverted_index.json.gz")

        # 保存未压缩版本（便于调试）
        self._atomic_write_json(index_path, index_data)

        # 保存压缩版本
        fd, temp_path = tempfile.mkstemp(prefix="inverted_", suffix=".tmp", dir=self.inverted_index_dir)
        os.close(fd)
        try:
            with gzip.open(temp_path, "wt", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False)
            os.replace(temp_path, compressed_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        print(f"[IndexBuilderV3] 倒排索引已保存到 {index_path}")

    def build_index(self, original_file_path: str) -> dict[str, Any]:
        """构建单个文件的索引（V2兼容接口）

        Args:
            original_file_path: 原始文件路径

        Returns:
            构建结果字典
        """
        result = {"success": False, "index_data": None, "error": ""}

        try:
            if not os.path.exists(original_file_path):
                result["error"] = f"文件不存在: {original_file_path}"
                return result

            filename = os.path.basename(original_file_path)
            file_id = os.path.splitext(filename)[0].replace(" ", "_").lower()

            self._load_registry()
            process_result = self._process_file(filename)

            if process_result["success"]:
                index_path = os.path.join(self.files_index_dir, f"{file_id}_index.json")
                with open(index_path, encoding="utf-8") as f:
                    index_data = json.load(f)

                result["index_data"] = index_data
                result["success"] = True
            else:
                result["error"] = process_result["error"]

            return result
        except Exception as e:
            result["error"] = str(e)
            return result

    def save_index(self, index_data: dict[str, Any], index_name: str = None) -> str:
        """保存索引文件（V2兼容接口）

        Args:
            index_data: 索引数据
            index_name: 索引文件名（可选）

        Returns:
            保存的索引文件路径
        """
        if index_name is None:
            file_id = index_data.get("file_id", "")
            index_name = f"{file_id}_index.json"

        index_path = os.path.join(self.files_index_dir, index_name)

        self._atomic_write_json(index_path, index_data)

        return index_path


if __name__ == "__main__":
    print("=" * 60)
    print("IndexBuilderV3 - 索引构建工具")
    print("=" * 60)

    builder = IndexBuilderV3()

    # 清除旧索引
    print("\n1. 清除旧索引...")
    clear_result = builder.clear_all_indexes()
    print(f"   删除了 {clear_result['deleted_files']} 个文件")

    # 构建所有索引
    print("\n2. 构建所有索引...")
    result = builder.build_all_indexes()

    if result["overall_success"]:
        print("\n✅ 索引构建成功！")
        print(f"   文件级索引: {result['file_indexes']['processed_files']} 个")
        print(f"   全局索引: {result['global_index']['indexed_files']} 个文件已索引")
    else:
        print("\n❌ 索引构建失败")
        if result["file_indexes"].get("error"):
            print(f"   文件级索引错误: {result['file_indexes']['error']}")
        if result["global_index"].get("error"):
            print(f"   全局索引错误: {result['global_index']['error']}")
