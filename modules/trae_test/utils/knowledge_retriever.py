"""知识库检索工具 v3.0 - 基于元数据标签的现代化检索实现"""

import glob as glob_mod
import gzip
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import joinedload

from modules.trae_test.core import cache_manager
from modules.trae_test.core.db_pool import get_session
from modules.trae_test.core.migration.schema import (
    KBBusinessRule,
    KBFile,
    KBProblem,
    KBRequirement,
)

logger = logging.getLogger(__name__)

from .business_rule_extractor import BusinessRuleExtractor
from .file_management_service import FileManagementService
from .file_repository import FileRepository
from .metadata_repository import MetadataRepository
from .path_utils import PathManager, find_project_root
from .rag_semantic import SemanticConfig, SemanticIndexer, validate_rag_environment

API_VERSION = "3.0.0"

# 模块名称与标签映射表（集中管理，新增模块只需修改此处）
MODULE_TAG_MAP: dict[str, list[str]] = {
    "产品": ["产品模块", "产品"],
    "销售": ["销售模块", "销售"],
    "采购": ["采购模块", "采购"],
    "物流": ["物流模块", "物流"],
    "财务": ["财务模块", "财务"],
    "系统": ["系统模块", "系统"],
    "维护": ["维护模块", "维护"],
    "WMS": ["WMS仓储", "WMS"],
    "WMS仓储": ["WMS仓储", "WMS"],
    "WMS PDA": ["WMS_PDA", "WMS"],
    "Dashboard": ["Dashboard", "Dashboard模块"],
}
MODULE_NAMES: list[str] = list(MODULE_TAG_MAP.keys())
DB_SEARCH_LIMIT = 50  # 数据库检索单表最大返回条数
_REGISTRY_REFRESH_INTERVAL = 3600  # 注册表刷新间隔（秒）


class KnowledgeRetriever:
    """知识库检索工具 v3.0 - 基于元数据标签的检索实现"""

    def __init__(self, api_version: str = "auto"):
        """初始化知识库检索工具

        Args:
            api_version: API版本，支持 "auto", "3.0.0"
        """
        self.knowledge_base_dir = PathManager.get_kb_base_dir()
        self.data_dir = PathManager.get_data_dir()
        self.original_dir = PathManager.get_original_dir()
        self.chunks_dir = PathManager.get_chunks_dir()
        self.index_dir = PathManager.get_index_dir()
        self.metadata_dir = PathManager.get_metadata_dir()

        self.registry_path = os.path.join(self.metadata_dir, "file_registry.json")

        self._file_repository = FileRepository(self.knowledge_base_dir)
        self._metadata_repository = MetadataRepository(self.knowledge_base_dir)
        self._rule_extractor = BusinessRuleExtractor()
        self._file_manager = FileManagementService()

        self._registry: dict[str, Any] | None = None
        self._file_cache: dict[str, Any] = {}
        self._index_cache: dict[str, Any] = {}

        self._rule_file_index: list[dict[str, Any]] = []
        self._rules_loaded = False

        self._db_enabled = bool(os.getenv("DATABASE_URL"))
        self._inverted_index_loaded = False
        self._prefix_index: dict[str, list[str]] = {}
        self._pages_cache: dict[str, list[dict[str, Any]]] | None = None
        self._registry_last_loaded: float = 0
        self._semantic_indexer: SemanticIndexer | None = None

        self._load_registry()

    # ── 内部辅助方法 ─────────────────────────────────────────────

    def _load_registry(self) -> None:
        """加载文件注册表 metadata/file_registry.json"""
        if not os.path.exists(self.registry_path):
            try:
                from .metadata_manager import MetadataManager

                MetadataManager(self.knowledge_base_dir).scan_and_register_all()
            except Exception as e:
                logger.warning("Failed to rebuild knowledge registry: %s", e)
        self._metadata_repository.load_registry()
        self._registry = self._metadata_repository.get_registry()
        self._registry_last_loaded = time.time()

    def _should_refresh_registry(self) -> bool:
        """判断是否需要刷新注册表"""
        return time.time() - self._registry_last_loaded > _REGISTRY_REFRESH_INTERVAL

    def refresh_registry(self) -> None:
        """刷新文件注册表，确保索引与物理文件一致"""
        logger.info("刷新文件注册表")
        self.clear_caches()
        self._load_registry()

    def _ensure_rules_loaded(self) -> None:
        """建立规则文件索引（仅扫描元数据，不加载文件内容）"""
        self._metadata_repository.ensure_rules_loaded()
        self._rule_file_index = self._metadata_repository.get_rule_file_index()
        self._rules_loaded = True

    def _get_file_by_id(self, file_id: str) -> dict[str, Any] | None:
        """根据文件ID获取文件信息"""
        return self._metadata_repository.get_file_by_id(file_id)

    def _get_files_by_tag(self, tag: str) -> list[dict[str, Any]]:
        """根据标签获取文件列表"""
        return self._metadata_repository.get_files_by_tag(tag)

    def _load_file_content(self, file_info: dict[str, Any]) -> dict[str, Any] | None:
        """加载文件内容（支持JSON和MD文件）"""
        return self._file_repository.load_file(file_info)

    def _search_by_tags(self, *tags: str) -> list[dict[str, Any]]:
        """按多个标签检索文件"""
        return self._metadata_repository.search_by_tags(*tags)

    def _search_single_file(self, *tags: str, title_filter: Callable | None = None) -> dict[str, Any]:
        """通用单文件搜索方法

        Args:
            *tags: 搜索标签
            title_filter: 可选的标题过滤函数，接收文件标题，返回布尔值

        Returns:
            文件内容字典，未找到返回空字典
        """
        files = self._search_by_tags(*tags)

        for file_info in files:
            if title_filter and not title_filter(file_info.get("title", "")):
                continue

            content = self._load_file_content(file_info)
            if content:
                return content
        return {}

    def _search_multiple_files(self, search_configs: list[dict[str, Any]]) -> dict[str, Any]:
        """通用多文件搜索与合并方法

        Args:
            search_configs: 搜索配置列表，每个配置包含：
                - tags: 搜索标签列表
                - title_filter: 标题过滤函数（可选）
                - result_key: 结果字典中的键名

        Returns:
            合并后的结果字典
        """
        result: dict[str, Any] = {}

        for config in search_configs:
            tags = config.get("tags", [])
            title_filter = config.get("title_filter")
            result_key = config.get("result_key")

            content = self._search_single_file(*tags, title_filter=title_filter)
            if content and result_key:
                result[result_key] = content

        return result

    # ── Redis 缓存 ───────────────────────────────────────────────

    def _build_cache_key(self, keyword: str, mode: str = "auto") -> str:
        """构造缓存键（含mode参数避免不同模式key冲突）"""
        return f"kb:search:{mode}:{hashlib.md5(keyword.encode(), usedforsecurity=False).hexdigest()}"

    def _search_cache(self, keyword: str, mode: str = "auto") -> Any:
        """通过 Redis 缓存检索"""
        if cache_manager is None:
            return None
        cache_key = self._build_cache_key(keyword, mode)
        return cache_manager.get_cached(cache_key)

    def _set_search_cache(self, keyword: str, result: Any, mode: str = "auto") -> None:
        """将检索结果写入 Redis 缓存"""
        if cache_manager is None:
            return
        if result is not None:
            cache_key = self._build_cache_key(keyword, mode)
            cache_manager.set_cached(cache_key, result, ttl=1800)

    # ── 数据库检索 ───────────────────────────────────────────────

    def _search_db(self, keyword: str) -> list[dict[str, Any]] | None:
        """通过 PostgreSQL 数据库检索（统一ILike + JOIN，消除N+1与优先级截断）

        Returns:
            合并后的结果列表，按 type 区分来源
        """
        if not self._db_enabled or get_session is None:
            return None

        session = None
        try:
            session = get_session()
            if session is None:
                logger.warning("Database session not available")
                return None
            pattern = f"%{keyword.lower()}%"
            results: list[dict[str, Any]] = []

            # 需求检索
            for r in (
                session.query(KBRequirement)
                .filter(KBRequirement.title.ilike(pattern) | KBRequirement.description.ilike(pattern))
                .limit(DB_SEARCH_LIMIT)
                .all()
            ):
                results.append(
                    {
                        "type": "requirement",
                        "file": r.file.title if r.file else "",
                        "module": r.module,
                        "title": r.title,
                        "data": r.data,
                    }
                )

            # 业务规则检索
            for r in (
                session.query(KBBusinessRule)
                .filter(KBBusinessRule.rule_name.ilike(pattern) | KBBusinessRule.rule_content.ilike(pattern))
                .limit(DB_SEARCH_LIMIT)
                .all()
            ):
                results.append(
                    {
                        "type": "business_rule",
                        "file": r.file.title if r.file else "",
                        "module": r.module,
                        "rule_name": r.rule_name,
                        "rule_content": r.rule_content,
                    }
                )

            # 问题检索
            for p in (
                session.query(KBProblem)
                .filter(KBProblem.problem_title.ilike(pattern) | KBProblem.problem_description.ilike(pattern))
                .limit(DB_SEARCH_LIMIT)
                .all()
            ):
                results.append(
                    {
                        "type": "problem",
                        "file": p.file.title if p.file else "",
                        "problem": p.problem_title,
                        "data": p.data,
                    }
                )

            # 文件标题/分类匹配（joinedload 一次性加载 chunks，消除 N+1）
            for f in (
                session.query(KBFile)
                .options(joinedload(KBFile.chunks))
                .filter(KBFile.title.ilike(pattern) | KBFile.classification.ilike(pattern))
                .limit(DB_SEARCH_LIMIT)
                .all()
            ):
                results.append(
                    {
                        "type": "module",
                        "file": f.title,
                        "classification": f.classification,
                        "chunks": [c.content for c in f.chunks],
                    }
                )

            return results if results else None

        finally:
            if session:
                session.close()

    # ── 公开检索接口 ─────────────────────────────────────────────

    def search_module(self, module_name: str) -> dict[str, Any]:
        """按模块名称检索业务规则（保持向后兼容）

        Args:
            module_name: 模块名称（如 销售、采购、产品、物流、财务、系统、维护）

        Returns:
            模块知识字典
        """
        tags = MODULE_TAG_MAP.get(module_name, [module_name])
        files = self._search_by_tags(*tags)

        for file_info in files:
            content = self._load_file_content(file_info)
            if content:
                return content

        return {}

    def search_cross_module_flows(self) -> dict[str, Any]:
        """检索跨模块全链路业务流程（保持向后兼容）

        Returns:
            全链路业务流程字典
        """
        return self._search_single_file(
            "全链路业务流程", "业务规则", title_filter=lambda title: "全链路" in title or "流程" in title
        )

    def search_test_template(self) -> dict[str, Any]:
        """检索测试用例模板规范（保持向后兼容）

        Returns:
            测试用例模板字典
        """
        return self._search_single_file("测试用例模板", "测试规范")

    def search_defect_spec(self) -> dict[str, Any]:
        """检索缺陷报告规范（保持向后兼容）

        Returns:
            缺陷报告规范字典
        """
        return self._search_single_file("缺陷报告规范", "测试规范")

    def search_navigation(self) -> dict[str, Any]:
        """检索ERP菜单导航与路由规范（保持向后兼容）

        Returns:
            导航规范字典
        """
        return self._search_single_file("导航规范", "ERP菜单导航")

    def search_automation_spec(self) -> dict[str, Any]:
        """检索自动化测试规范（保持向后兼容）

        Returns:
            自动化规范字典
        """
        search_configs = [
            {
                "tags": ["技术栈", "自动化规范"],
                "title_filter": lambda title: "技术栈" in title,
                "result_key": "技术栈与工程结构",
            },
            {
                "tags": ["脚本编写规范", "自动化规范"],
                "title_filter": lambda title: "脚本编写" in title,
                "result_key": "脚本编写规范",
            },
            {
                "tags": ["DOM", "Playwright", "自动化规范"],
                "title_filter": lambda title: "DOM" in title or "Playwright" in title,
                "result_key": "销售订单列表DOM与Playwright定位",
            },
        ]

        return self._search_multiple_files(search_configs)

    def _lazy_load_module_pages(self, module_name: str) -> None:
        """延迟加载单个模块的 pages 数据到缓存"""
        if self._pages_cache is None:
            self._pages_cache = {}
        if module_name in self._pages_cache:
            return
        module_data = self.search_module(module_name)
        pages = module_data.get("pages", [])
        if pages:
            self._pages_cache[module_name] = pages
            logger.debug("缓存模块[%s]的页面数据，共%d个页面", module_name, len(pages))

    def search_page_info(self, page_name: str) -> list[dict[str, Any]]:
        """按页面名称检索页面信息（保持向后兼容）

        Args:
            page_name: 页面名称关键词（如 销售订单、采购补货）

        Returns:
            匹配的页面信息列表
        """
        if not page_name:
            return []

        page_name_lower = page_name.lower()
        results: list[dict[str, Any]] = []

        for module_name in MODULE_NAMES:
            self._lazy_load_module_pages(module_name)
            pages = self._pages_cache.get(module_name, [])
            for page in pages:
                path = page.get("path", "").lower()
                name = page.get("name", "").lower()
                if page_name_lower in path or page_name_lower in name:
                    results.append({"module": module_name, **page})

        logger.info("页面检索完成，关键词'%s'匹配到%d条结果", page_name, len(results))
        return results

    def search_business_rules(self, keyword: str) -> list[dict[str, Any]]:
        """按关键词检索业务规则（按需加载，避免全量预加载）

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的业务规则列表
        """
        if not keyword:
            return []

        self._ensure_rules_loaded()

        keyword_lower = keyword.lower()

        candidate_files: list[dict[str, Any]] = []
        for file_info in self._rule_file_index:
            title = file_info["title"].lower()
            classification = file_info["classification"].lower()
            if keyword_lower in title or keyword_lower in classification:
                candidate_files.append(file_info)

        # Prefer indexed chunk sources when metadata is not selective enough.
        # This keeps the existing rule-level verification while avoiding a
        # full-file scan for terms already present in the inverted index.
        if not candidate_files:
            indexed_hits = self.search_by_inverted_index(keyword, top_k=100)
            source_names = {os.path.basename(hit.get("source_file", "")) for hit in indexed_hits}
            if source_names:
                candidate_files = [
                    file_info
                    for file_info in self._rule_file_index
                    if any(
                        name.startswith(os.path.splitext(os.path.basename(file_info["original_path"]))[0])
                        for name in source_names
                    )
                ]
                if candidate_files:
                    logger.info("关键词 '%s' 通过倒排索引定位到 %d 个候选文件", keyword, len(candidate_files))

        if not candidate_files:
            logger.warning(
                "关键词 '%s' 未匹配到任何文件元数据，降级为全量规则扫描（%d 个文件）",
                keyword,
                len(self._rule_file_index),
            )
            candidate_files = self._rule_file_index

        results: list[dict[str, Any]] = []
        for file_info in candidate_files:
            content = self._load_file_content(file_info)
            if not content:
                continue
            rules = self._rule_extractor.extract_rules(content)
            for rule in rules:
                if self._rule_extractor.match_keyword_in_rule(rule, keyword):
                    result_item: dict[str, Any] = {
                        "file_id": file_info["file_id"],
                        "file_title": file_info["title"],
                        "module": file_info["classification"],
                    }
                    if isinstance(rule, dict):
                        result_item.update(rule)
                    else:
                        result_item["rule"] = rule
                    results.append(result_item)

        return results

    def search_requirements(self, keyword: str = "", module: str = "") -> list[dict[str, Any]]:
        """检索需求清单（保持向后兼容）

        Args:
            keyword: 搜索关键词（匹配标题、描述、评论）
            module: 模块名称（如 ERP采购模块、ERP销售订单模块）

        Returns:
            匹配的需求列表
        """
        files = self._search_by_tags("需求清单", "业务规则")
        for file_info in files:
            if "需求" in file_info.get("title", ""):
                content = self._load_file_content(file_info)
                if content:
                    results: list[dict[str, Any]] = []
                    req_by_module = content.get("requirements_by_module", {})
                    for mod_name, mod_data in req_by_module.items():
                        if module and module not in mod_name:
                            continue
                        for item in mod_data.get("items", []):
                            if not keyword:
                                results.append({"module": mod_name, **item})
                            else:
                                title = item.get("title", "")
                                desc = item.get("description", "")
                                comments = item.get("comments", "")
                                if keyword in title or keyword in desc or keyword in comments:
                                    results.append({"module": mod_name, **item})
                    return results

        return []

    # ── 索引与文件信息 ───────────────────────────────────────────

    def get_index(self) -> dict[str, Any]:
        """获取知识库主索引（优先使用v3.0全局索引，回退到旧版索引）

        Returns:
            索引字典
        """
        global_index_path = os.path.join(self.knowledge_base_dir, "index", "global", "global_index.json")
        if os.path.exists(global_index_path):
            with open(global_index_path, encoding="utf-8") as f:
                index = json.load(f)
            registry_ids = set(self.list_available_files())
            index_ids = {item.get("file_id") for item in index.get("files", []) if isinstance(item, dict)}
            index["index_status"] = {
                "valid": registry_ids == index_ids,
                "missing_files": sorted(registry_ids - index_ids),
                "stale_files": sorted(index_ids - registry_ids),
            }
            return index

        legacy_index_path = os.path.join(self.knowledge_base_dir, "index.json")
        if os.path.exists(legacy_index_path):
            with open(legacy_index_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def list_available_files(self) -> list[str]:
        """列出所有可用的文件（替代原 list_available_indexes）

        Returns:
            文件名列表
        """
        return self._metadata_repository.list_available_files()

    def get_all_chunks(self, file_title: str, max_chunks: int | None = None) -> list[dict[str, Any]]:
        """获取文件的所有内容块

        Args:
            file_title: 文件标题（如 销售模块、需求清单）
            max_chunks: 最大返回块数，None表示不限制

        Returns:
            块数据列表，按 chunk_index 排序
        """
        chunks = self._file_repository.get_all_chunks(file_title)
        if max_chunks is not None and len(chunks) > max_chunks:
            logger.warning("get_all_chunks: 文件[%s]共有%d个chunk，已截断为%d个", file_title, len(chunks), max_chunks)
            return chunks[:max_chunks]
        return chunks

    def get_chunk_by_id(self, file_title: str, chunk_index: int) -> dict[str, Any] | None:
        """按索引获取单个块

        Args:
            file_title: 文件标题
            chunk_index: 块索引（从0开始）

        Returns:
            块数据字典，不存在返回None
        """
        return self._file_repository.get_chunk_by_id(file_title, chunk_index)

    def load_aggregated_data(self, file_title: str) -> dict[str, Any] | None:
        """加载文件的完整聚合数据（优先使用块文件，回退到原始文件）

        Args:
            file_title: 文件标题

        Returns:
            聚合后的完整数据
        """
        return self._file_repository.load_aggregated_data(file_title)

    # ── 缓存管理 ─────────────────────────────────────────────────

    def clear_caches(self) -> None:
        """清除所有缓存"""
        self._file_cache.clear()
        self._index_cache.clear()
        self._rule_file_index.clear()
        self._rules_loaded = False
        self._inverted_index_loaded = False
        self._prefix_index.clear()
        self._pages_cache = None
        self._file_repository.clear_cache()
        self._metadata_repository.clear_rule_index()

    # ── 文件管理 ─────────────────────────────────────────────────

    def add_file(self, file_path: str, auto_process: bool = True) -> dict[str, Any]:
        """添加新文件到知识库

        将文件复制到 data/original/ 目录，自动触发分割和索引构建，
        并更新文件注册表。

        Args:
            file_path: 源文件路径
            auto_process: 是否自动处理（分割+索引）

        Returns:
            处理结果字典，包含 success、file_title、split_result、index_result 等字段
        """
        return self._file_manager.add_file(
            file_path, auto_process, clear_caches_callback=self.clear_caches, load_registry_callback=self._load_registry
        )

    def update_file(self, file_path: str, auto_process: bool = True) -> dict[str, Any]:
        """更新现有文件并重建索引

        覆盖 data/original/ 中的对应文件，重新分割并重建索引，
        同步更新文件注册表。

        Args:
            file_path: 源文件路径（用于更新知识库中的对应文件）
            auto_process: 是否自动处理（分割+索引）

        Returns:
            处理结果字典
        """
        return self._file_manager.update_file(
            file_path, auto_process, clear_caches_callback=self.clear_caches, load_registry_callback=self._load_registry
        )

    # ── 智能检索 ─────────────────────────────────────────────────

    def _get_semantic_indexer(self) -> SemanticIndexer:
        if self._semantic_indexer is None:
            self._semantic_indexer = SemanticIndexer(SemanticConfig.from_env())
        return self._semantic_indexer

    def retrieve_semantic(
        self,
        keyword: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """语义检索接口（RAG PoC 增强层）。

        原有 retrieve() 默认行为保持不变；调用方需要显式使用 semantic/hybrid。
        """
        if not keyword:
            return []
        validate_rag_environment()
        return self._get_semantic_indexer().search(
            keyword.strip(),
            top_k=top_k,
            threshold=similarity_threshold,
        )

    def retrieve_hybrid(
        self,
        keyword: str,
        top_k: int = 10,
        semantic_weight: float = 0.6,
        lexical_weight: float = 0.4,
    ) -> list[dict[str, Any]]:
        """混合检索：倒排索引 + 语义检索合并重排。"""
        if not keyword:
            return []
        validate_rag_environment()

        semantic_results = self.retrieve_semantic(keyword, top_k=top_k)
        lexical_results = self.search_by_inverted_index(keyword, top_k=top_k)

        ranked: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(semantic_results):
            key = item.get("chunk_id") or item.get("id") or f"semantic:{index}"
            merged = dict(item)
            merged["retrieval_sources"] = ["semantic"]
            merged["hybrid_score"] = semantic_weight * float(item.get("similarity_score", 0))
            ranked[str(key)] = merged

        for index, item in enumerate(lexical_results):
            key = item.get("chunk_id") or f"lexical:{index}"
            score = float(item.get("similarity_score", item.get("weight", 0)) or 0)
            normalized = min(score, 1.0)
            if str(key) in ranked:
                ranked[str(key)]["retrieval_sources"].append("lexical")
                ranked[str(key)]["hybrid_score"] += lexical_weight * normalized
            else:
                merged = dict(item)
                merged["retrieval_sources"] = ["lexical"]
                merged["hybrid_score"] = lexical_weight * normalized
                ranked[str(key)] = merged

        results = list(ranked.values())
        results.sort(key=lambda item: item.get("hybrid_score", 0), reverse=True)
        return results[:top_k]

    def retrieve(self, keyword: str, mode: str = "auto") -> Any:
        """智能检索接口 - 按关键词检索知识库内容

        Args:
            keyword: 搜索关键词
            mode: 检索模式
                - "auto": 自动选择最佳检索方式（默认）
                - "module": 按模块检索
                - "rules": 检索业务规则
                - "requirements": 检索需求清单
                - "semantic": 语义检索（显式启用）
                - "hybrid": 倒排 + 语义混合检索（显式启用）

        Returns:
            检索结果
        """
        if not keyword:
            return None

        keyword = keyword.strip()

        if self._should_refresh_registry():
            self.refresh_registry()

        if mode == "module":
            if keyword in MODULE_NAMES:
                return self.search_module(keyword)
            for module_name in MODULE_NAMES:
                if keyword in module_name:
                    return self.search_module(module_name)
            return None

        if mode == "rules":
            return self.search_business_rules(keyword)

        if mode == "requirements":
            return self.search_requirements(keyword=keyword)

        if mode == "semantic":
            return self.retrieve_semantic(keyword)

        if mode == "hybrid":
            return self.retrieve_hybrid(keyword)

        # auto 模式
        cache_result = self._search_cache(keyword, mode="auto")
        if cache_result is not None:
            return cache_result

        db_result = self._search_db(keyword)
        if db_result is not None:
            self._set_search_cache(keyword, db_result, mode="auto")
            return db_result

        result = None
        if keyword in MODULE_NAMES:
            result = self.search_module(keyword)
        else:
            for module_name in MODULE_NAMES:
                if keyword in module_name:
                    result = self.search_module(module_name)
                    break

        if not result:
            result = self.search_business_rules(keyword)
        if not result:
            result = self.search_requirements(keyword=keyword)
        if not result and ("流程" in keyword or "链路" in keyword):
            result = self.search_cross_module_flows()
        if not result:
            result = self.search_by_inverted_index(keyword)

        if result:
            self._set_search_cache(keyword, result, mode="auto")

        return result or None

    def batch_retrieve(self, keywords: list[str], mode: str = "auto") -> dict[str, Any]:
        """批量检索接口

        Args:
            keywords: 关键词列表
            mode: 检索模式

        Returns:
            检索结果字典，key为关键词
        """
        results: dict[str, Any] = {}
        for kw in keywords:
            results[kw] = self.retrieve(kw, mode)
        return results

    # ── 统计信息 ─────────────────────────────────────────────────

    def get_retrieval_stats(self) -> dict[str, Any]:
        """获取检索统计信息

        Returns:
            统计信息字典
        """
        registry_stats = self._metadata_repository.get_registry_stats()

        return {
            "cache_stats": {
                "file_cache_size": self._file_repository.get_file_cache_size(),
                "index_cache_size": len(self._index_cache),
            },
            "registry_stats": registry_stats,
            "registry_loaded": self._registry is not None,
            "api_version": API_VERSION,
        }

    def get_compatibility_info(self) -> dict[str, Any]:
        """获取兼容性信息

        Returns:
            兼容性信息字典
        """
        original_count = 0
        if os.path.exists(self.original_dir):
            original_count = len([f for f in os.listdir(self.original_dir) if f.endswith(".json")])

        registry_stats = self._metadata_repository.get_registry_stats()

        return {
            "api_version": API_VERSION,
            "architecture_version": "3.0",
            "file_counts": {"original_files": original_count, "registered_files": registry_stats["total_files"]},
            "registry_available": self._registry is not None,
        }

    def ensure_compatibility(self) -> dict[str, Any]:
        """确保兼容性

        Returns:
            兼容性检查结果
        """
        info = self.get_compatibility_info()

        if not self._registry:
            logger.warning("文件注册表未加载")

        return info

    # ── 倒排索引 ─────────────────────────────────────────────────

    def search_historical_cases(self, keyword: str, top_k: int = 3) -> list[dict[str, Any]]:
        """检索历史测试用例（双源：知识库JSON + workspace Excel）

        通过学习已有用例的步骤和预期结果中的高频模式，优化生成策略。

        Args:
            keyword: 匹配关键词
            top_k: 返回的最大结果数

        Returns:
            历史用例列表，每条包含 {steps, expected_result, source, case_name}
        """
        results: list[dict[str, Any]] = []

        # ── 源1：知识库 JSON ──────────────────────────────────
        json_content = self._search_single_file(
            "已学习测试用例详情", "测试用例", title_filter=lambda t: "已学习测试用例" in t
        )
        if json_content and "requirements" in json_content:
            keyword_lower = keyword.lower()
            for req in json_content["requirements"]:
                for case in req.get("cases", []):
                    case_name = case.get("用例名称", "")
                    steps = case.get("用例步骤", "")
                    expected = case.get("预期结果", "")
                    if keyword_lower in case_name.lower() or keyword_lower in steps.lower():
                        results.append(
                            {
                                "source": "knowledge_base",
                                "case_name": case_name,
                                "steps": steps.strip(),
                                "expected_result": expected.strip(),
                            }
                        )
                        if len(results) >= top_k:
                            break
                if len(results) >= top_k:
                    break

        # ── 源2：workspace Excel ─────────────────────────────
        if len(results) < top_k:
            try:
                results.extend(self._search_workspace_excel(keyword, top_k - len(results)))
            except Exception:
                logger.warning("历史用例-工作区Excel检索失败，跳过", exc_info=True)

        return results[:top_k]

    def _search_workspace_excel(self, keyword: str, top_k: int) -> list[dict[str, Any]]:
        """从 workspace/YYYYMMDD/ 目录下最近30天的 Excel 中检索。"""
        from datetime import datetime, timedelta

        project_root = find_project_root(__file__)
        workspace_dir = os.path.join(project_root, "workspace")

        results: list[dict[str, Any]] = []
        if not os.path.isdir(workspace_dir):
            return results

        cutoff = datetime.now() - timedelta(days=30)
        keyword_lower = keyword.lower()

        # 只扫描 workspace/YYYYMMDD/*.xlsx，日期目录下不再使用子目录。
        from .excel_generator import ExcelGenerator

        patterns = [os.path.join(workspace_dir, "[0-9]" * 8, "*.xlsx")]
        excel_paths = sorted(
            {path for pattern in patterns for path in glob_mod.iglob(pattern, recursive=True)},
            reverse=True,
        )
        for excel_path in excel_paths:
            try:
                mod_time = datetime.fromtimestamp(os.path.getmtime(excel_path))
                if mod_time < cutoff:
                    continue  # 只读最近30天
            except OSError:
                continue

            cases = ExcelGenerator.read_excel_worksheet(excel_path)
            for case in cases:
                if keyword_lower in case["case_name"].lower() or keyword_lower in case["steps"].lower():
                    case["source"] = f"workspace:{os.path.basename(excel_path)}"
                    results.append(case)
                    if len(results) >= top_k:
                        return results

        return results

    def search_by_inverted_index(self, keyword: str, top_k: int = 10) -> list[dict[str, Any]]:
        """通过倒排索引检索

        使用精确匹配 + 前缀索引查找（O(1)），避免全量遍历所有关键词。

        Args:
            keyword: 搜索关键词
            top_k: 返回结果数量限制

        Returns:
            匹配的chunk信息列表
        """
        if not keyword:
            return []

        if not self._inverted_index_loaded:
            self._load_inverted_index()

        inverted_index = self._index_cache.get("inverted_index", {})
        if not inverted_index:
            return []

        index_data = inverted_index.get("index", {})
        if not index_data:
            return []

        kw_lower = keyword.lower()
        kw_upper = keyword.upper()

        results: list[dict[str, Any]] = []

        # 1. 精确匹配（O(1)）
        if keyword in index_data:
            results.extend(index_data[keyword])
        if kw_upper in index_data and kw_upper != keyword:
            results.extend(index_data[kw_upper])

        # 2. 前缀匹配（通过前缀索引 O(1) 查找，避免全量遍历）
        # 方向一：搜索词是索引词的前缀（如搜"销"匹配"销售"）
        if kw_lower in self._prefix_index:
            for matched_key in self._prefix_index[kw_lower]:
                if matched_key != keyword and matched_key != kw_upper:
                    results.extend(index_data.get(matched_key, []))

        # 方向二：索引词是搜索词的前缀（如搜"销售订单"匹配"销售"）
        for i in range(1, len(kw_lower)):
            prefix = kw_lower[:i]
            if prefix in index_data and prefix != keyword and prefix != kw_upper:
                results.extend(index_data[prefix])

        # Chinese business terms are often embedded in a longer indexed
        # phrase (for example, "修改告警任务"). Use the index keys as the
        # bounded fallback before scanning knowledge files.
        if not results:
            for indexed_key, entries in index_data.items():
                if kw_lower in indexed_key.lower():
                    results.extend(entries)
                    if len(results) >= top_k * 5:
                        break

        if not results:
            return []

        # 去重 + 排序
        seen_chunk_ids: set = set()
        unique_results: list[dict[str, Any]] = []
        for entry in results:
            chunk_id = entry["chunk_id"]
            if chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                unique_results.append(entry)

        unique_results.sort(key=lambda x: -x.get("weight", 0))

        if top_k > 0:
            unique_results = unique_results[:top_k]

        return self._load_chunk_details(unique_results)

    def _load_inverted_index(self) -> None:
        """加载倒排索引（含错误恢复标记）"""
        inverted_index_path = os.path.join(self.knowledge_base_dir, "index", "inverted", "inverted_index.json")
        compressed_path = os.path.join(self.knowledge_base_dir, "index", "inverted", "inverted_index.json.gz")

        data = None

        if os.path.exists(inverted_index_path):
            try:
                with open(inverted_index_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error("加载倒排索引失败: %s", e)

        if data is None and os.path.exists(compressed_path):
            try:
                with gzip.open(compressed_path, "rt", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error("加载压缩倒排索引失败: %s", e)

        if data:
            self._index_cache["inverted_index"] = data
            self._inverted_index_loaded = True
            # 构建前缀索引（O(1) 前缀查找）
            self._prefix_index.clear()
            for key in data.get("index", {}):
                for i in range(1, len(key) + 1):
                    prefix = key[:i]
                    if prefix not in self._prefix_index:
                        self._prefix_index[prefix] = []
                    self._prefix_index[prefix].append(key)
            logger.info("倒排索引已加载，包含 %d 个关键词", data.get("total_keywords", 0))
        else:
            self._inverted_index_loaded = True  # 标记已尝试过，避免重复IO

    def _load_chunk_details(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """加载chunk的详细内容

        Args:
            entries: 倒排索引条目列表

        Returns:
            包含完整chunk内容的结果列表
        """
        chunks_dir = PathManager.get_chunks_dir()

        results: list[dict[str, Any]] = []

        for entry in entries:
            source_file = entry.get("source_file", "")
            chunk_path = os.path.join(chunks_dir, source_file)

            if os.path.exists(chunk_path):
                try:
                    with open(chunk_path, encoding="utf-8") as f:
                        chunk = json.load(f)

                    result = {
                        "chunk_id": entry["chunk_id"],
                        "similarity_score": entry.get("weight", 0),
                        "source_file": source_file,
                        "metadata": chunk.get("metadata", {}),
                        "content": chunk.get("content", {}),
                        "snippet": self._extract_snippet(chunk, entry.get("field", "")),
                    }
                    results.append(result)
                except Exception as e:
                    logger.error("加载chunk失败 %s: %s", source_file, e)

        return results

    def _extract_snippet(self, chunk: dict[str, Any], field: str) -> str:
        """提取检索结果的摘要片段

        Args:
            chunk: chunk内容
            field: 匹配字段

        Returns:
            摘要片段
        """
        content = chunk.get("content", {})
        rule_name = content.get("rule_name", "")
        description = content.get("rule_description", "")

        snippet = rule_name
        if description:
            if snippet:
                snippet += " - "
            snippet += description

        if len(snippet) > 150:
            snippet = snippet[:150] + "..."

        return snippet
