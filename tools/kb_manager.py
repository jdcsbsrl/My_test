#!/usr/bin/env python3
"""知识库管理CLI工具 - 支持批量操作、分割、索引、验证和迁移"""

import argparse
import hashlib
import json
import logging
import os
import sys
import unicodedata
from typing import Any, Dict, Iterable

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 修复 Windows 终端 GBK 编码对 Unicode 符号的支持
if sys.platform == "win32":
    import io

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

OK_SIGN = "[OK]"
FAIL_SIGN = "[FAIL]"
CHECK_SIGN = "[v]"
CROSS_SIGN = "[x]"

logger = logging.getLogger(__name__)

from modules.trae_test.utils.file_splitter import JSONFileSplitter
from modules.trae_test.utils.index_builder_v3 import IndexBuilderV3
from modules.trae_test.utils.kb_monitor import KnowledgeBaseMonitor
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
from modules.trae_test.utils.metadata_manager import MetadataManager
from modules.trae_test.utils.rag_semantic import SemanticIndexer


class KnowledgeBaseManager:
    """知识库管理器，提供各种管理功能"""

    LIFECYCLE_STATUSES = frozenset({"draft", "active", "deprecated", "superseded"})

    def __init__(self):
        """初始化管理器"""
        self.monitor = KnowledgeBaseMonitor()
        self.splitter = JSONFileSplitter()
        self.index_builder = IndexBuilderV3()
        self.retriever = KnowledgeRetriever()

    def list_files(self) -> Dict:
        """列出所有知识库文件

        Returns:
            文件列表字典
        """
        result = {"original": [], "content": [], "index": [], "summary": {}}

        if os.path.exists(self.monitor.ORIGINAL_DIR):
            for filename in os.listdir(self.monitor.ORIGINAL_DIR):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.monitor.ORIGINAL_DIR, filename)
                    size = os.path.getsize(file_path)
                    result["original"].append({"filename": filename, "size": size, "size_kb": round(size / 1024, 2)})

        if os.path.exists(self.monitor.CONTENT_DIR):
            for filename in os.listdir(self.monitor.CONTENT_DIR):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.monitor.CONTENT_DIR, filename)
                    size = os.path.getsize(file_path)
                    result["content"].append({"filename": filename, "size": size, "size_kb": round(size / 1024, 2)})

        if os.path.exists(self.monitor.INDEX_DIR):
            for root, _, filenames in os.walk(self.monitor.INDEX_DIR):
                for filename in filenames:
                    if not filename.endswith((".json", ".gz")):
                        continue
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, self.monitor.INDEX_DIR).replace(os.sep, "/")
                    size = os.path.getsize(file_path)
                    result["index"].append({"filename": relative_path, "size": size, "size_kb": round(size / 1024, 2)})

        for files in result.values():
            if isinstance(files, list):
                files.sort(key=lambda item: item["filename"])

        result["summary"] = {
            "original_count": len(result["original"]),
            "content_count": len(result["content"]),
            "index_count": len(result["index"]),
            "original_size_kb": round(sum(file["size"] for file in result["original"]) / 1024, 2),
            "content_size_kb": round(sum(file["size"] for file in result["content"]) / 1024, 2),
            "index_size_kb": round(sum(file["size"] for file in result["index"]) / 1024, 2),
        }
        result["summary"]["total_size_kb"] = round(
            result["summary"]["original_size_kb"]
            + result["summary"]["content_size_kb"]
            + result["summary"]["index_size_kb"],
            2,
        )

        return result

    def split_file(self, file_path: str, force: bool = False) -> Dict:
        """分割单个文件

        Args:
            file_path: 文件路径
            force: 是否强制分割（忽略阈值）

        Returns:
            分割结果
        """
        if force:
            original_threshold = self.splitter.size_threshold
            self.splitter.size_threshold = 0
            result = self.splitter.split_file(file_path)
            self.splitter.size_threshold = original_threshold
            return result
        else:
            return self.splitter.split_file(file_path)

    def index_file(self, file_path: str) -> Dict:
        """为文件构建索引

        Args:
            file_path: 文件路径

        Returns:
            索引结果
        """
        result = self.index_builder.build_index(file_path)
        if result["success"] and result["index_data"]:
            index_path = self.index_builder.save_index(result["index_data"])
            result["index_path"] = index_path
        return result

    def _sync_secondary_indexes(self) -> Dict:
        """Rebuild only derived indexes after a successful source-file lifecycle step."""
        global_result = self.index_builder.build_global_index()
        if not global_result.get("success"):
            return {"success": False, "global": global_result, "inverted": {}, "error": global_result.get("error", "")}
        inverted_result = self.index_builder.build_inverted_index()
        return {
            "success": bool(inverted_result.get("success")),
            "global": global_result,
            "inverted": inverted_result,
            "error": inverted_result.get("error", ""),
        }

    def _refresh_retriever_state(self) -> Dict:
        """Discard retriever caches after derived indexes have been rebuilt.

        ``refresh_registry`` clears the registry, file, rule, and inverted-index
        caches before loading the current registry.  Keeping this step separate
        from index construction makes a successful lifecycle operation mean the
        manager's retriever can immediately observe the newly written indexes.
        """
        try:
            self.retriever.refresh_registry()
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    def validate_rule_contract(document: Any, strict: bool = False) -> Dict:
        """Validate structured ``business_rules`` identifiers and retrieval keywords.

        Legacy knowledge files deliberately remain valid in non-strict mode.  A
        strict caller (new JSON migration or an explicitly requested update)
        receives actionable errors instead of allowing an entry that cannot be
        asserted by rule id and business keyword after import.
        """
        result = {"success": True, "strict": strict, "checked_rules": 0, "errors": [], "warnings": []}
        if not isinstance(document, dict):
            message = "structured knowledge document must be a JSON object"
            (result["errors"] if strict else result["warnings"]).append(message)
            result["success"] = not strict
            return result

        rules = document.get("business_rules")
        if rules is None:
            message = "missing business_rules"
            (result["errors"] if strict else result["warnings"]).append(message)
            result["success"] = not strict
            return result
        if not isinstance(rules, list):
            message = "business_rules must be a list"
            (result["errors"] if strict else result["warnings"]).append(message)
            result["success"] = not strict
            return result
        if strict and not rules:
            result["errors"].append("business_rules must contain at least one rule")

        seen_rule_ids: set[str] = set()
        rule_id_by_index: dict[int, str] = {}
        for index, rule in enumerate(rules):
            location = f"business_rules[{index}]"
            if not isinstance(rule, dict):
                message = f"{location} must be an object"
                (result["errors"] if strict else result["warnings"]).append(message)
                continue
            result["checked_rules"] += 1
            rule_id = rule.get("rule_id")
            keywords = rule.get("keywords")
            content = rule.get("content")
            if not isinstance(rule_id, str) or not rule_id.strip():
                (result["errors"] if strict else result["warnings"]).append(
                    f"{location}.rule_id must be a non-empty string"
                )
            elif rule_id in seen_rule_ids:
                (result["errors"] if strict else result["warnings"]).append(f"duplicate rule_id: {rule_id}")
            else:
                seen_rule_ids.add(rule_id)
                rule_id_by_index[index] = rule_id
            if (
                not isinstance(keywords, list)
                or not keywords
                or any(not isinstance(item, str) or not item.strip() for item in keywords)
            ):
                (result["errors"] if strict else result["warnings"]).append(
                    f"{location}.keywords must be a non-empty list of non-empty strings"
                )
            if strict and (not isinstance(content, str) or not content.strip()):
                result["errors"].append(f"{location}.content must be a non-empty string")

        # Lifecycle metadata is optional for compatibility with existing
        # knowledge.  When present, it is validated without attempting any
        # automatic status transition, merge, or deletion.
        same_file_rule_ids = set(rule_id_by_index.values())
        lifecycle_warnings: list[str] = []
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            location = f"business_rules[{index}]"
            rule_id = rule_id_by_index.get(index, "")
            status_present = "status" in rule
            status = rule.get("status")
            normalized_status = status.strip() if isinstance(status, str) else None
            if status_present and normalized_status not in KnowledgeBaseManager.LIFECYCLE_STATUSES:
                issue = (
                    f"{location}.status must be one of: "
                    f"{', '.join(sorted(KnowledgeBaseManager.LIFECYCLE_STATUSES))}"
                )
                (result["errors"] if strict else result["warnings"]).append(issue)
                normalized_status = None

            supersedes_present = "supersedes" in rule
            supersedes = rule.get("supersedes")
            if supersedes_present and (
                not isinstance(supersedes, list)
                or any(not isinstance(item, str) or not item.strip() for item in supersedes)
                or len(set(supersedes)) != len(supersedes)
            ):
                issue = f"{location}.supersedes must be a list of unique non-empty rule_id strings"
                (result["errors"] if strict else result["warnings"]).append(issue)
                supersedes = []

            if normalized_status == "superseded" and not supersedes:
                issue = f"{location}.supersedes is required when status is superseded"
                (result["errors"] if strict else result["warnings"]).append(issue)

            if isinstance(supersedes, list):
                normalized_targets = [item.strip() for item in supersedes if isinstance(item, str) and item.strip()]
                if rule_id and rule_id in normalized_targets:
                    issue = f"{location}.supersedes must not reference its own rule_id: {rule_id}"
                    (result["errors"] if strict else result["warnings"]).append(issue)
                for target in normalized_targets:
                    if target not in same_file_rule_ids:
                        lifecycle_warnings.append(
                            f"{location}.supersedes target not found in this file; "
                            f"verify cross-file reference: {target}"
                        )

        if lifecycle_warnings:
            # Keep the historical result shape unchanged for documents that do
            # not use lifecycle metadata, while exposing cross-file checks when
            # they are relevant to the caller.
            result["lifecycle_warnings"] = lifecycle_warnings

        result["success"] = not result["errors"]
        return result

    @classmethod
    def validate_rule_contract_file(cls, file_path: str, strict: bool = False) -> Dict:
        """Validate a JSON knowledge source without changing it.

        Markdown and other unstructured legacy sources are explicitly skipped;
        the contract only applies to structured rule documents.
        """
        result = {
            "success": True,
            "file_path": file_path,
            "strict": strict,
            "skipped": False,
            "errors": [],
            "warnings": [],
        }
        if not file_path.lower().endswith(".json"):
            result["skipped"] = True
            return result
        try:
            with open(file_path, encoding="utf-8") as source:
                document = json.load(source)
        except (OSError, json.JSONDecodeError) as exc:
            result.update({"success": False, "errors": [f"invalid json: {exc}"]})
            return result
        result.update(cls.validate_rule_contract(document, strict=strict))
        result["file_path"] = file_path
        return result

    def process_file(self, file_path: str, sync_vector: bool = False, strict_rules: bool = False) -> Dict:
        """完整处理文件（分割+索引）

        Args:
            file_path: 文件路径

        Returns:
            处理结果
        """
        if strict_rules:
            contract = self.validate_rule_contract_file(file_path, strict=True)
            if not contract["success"]:
                return {
                    "success": False,
                    "file_path": file_path,
                    "rule_contract": contract,
                    "error": "rule contract validation failed",
                }

        result = self.monitor.process_file_complete(file_path)
        if strict_rules:
            result["rule_contract"] = contract
        if result.get("success"):
            result["secondary_indexes"] = self._sync_secondary_indexes()
            if not result["secondary_indexes"]["success"]:
                result["success"] = False
                result["error"] = result["secondary_indexes"].get("error", "二级索引同步失败")
        if result.get("success"):
            result["retriever_refresh"] = self._refresh_retriever_state()
            if not result["retriever_refresh"]["success"]:
                result["success"] = False
                result["error"] = result["retriever_refresh"].get("error", "检索缓存刷新失败")
        if result.get("success") and sync_vector:
            result["vector"] = self.sync_vector_file(file_path)
        return result

    def sync_vector_file(self, file_path: str) -> Dict:
        """将指定知识文件的 chunks 同步到本地语义向量索引。"""
        file_title = os.path.splitext(os.path.basename(file_path))[0]
        try:
            self.retriever.refresh_registry()
            chunks = self.retriever.get_all_chunks(file_title)
            if not chunks:
                content = self.retriever.load_aggregated_data(file_title)
                if content:
                    chunks = [
                        {
                            "chunk_id": file_title,
                            "metadata": {"file_title": file_title, "source_file": os.path.basename(file_path)},
                            "content": content,
                        }
                    ]
            if not chunks:
                return {"success": False, "file_title": file_title, "indexed": 0, "error": "no chunks found"}
            indexed = SemanticIndexer().index_chunks(chunks, source_file=os.path.basename(file_path))
            return {"success": True, "file_title": file_title, "indexed": indexed}
        except Exception as exc:
            return {"success": False, "file_title": file_title, "indexed": 0, "error": str(exc)}

    def verify_file(self, file_title: str) -> Dict:
        """验证文件完整性

        Args:
            file_title: 文件标题（不带扩展名）

        Returns:
            验证结果
        """
        result = {
            "success": False,
            "file_title": file_title,
            "index_exists": False,
            "chunks_exist": False,
            "chunks_valid": [],
            "error": "",
        }

        try:
            index_file = f"{file_title}_index.json"
            index_paths = [
                os.path.join(self.monitor.INDEX_DIR, "files", index_file),
                os.path.join(self.monitor.INDEX_DIR, index_file),
            ]
            result["index_exists"] = any(os.path.exists(path) for path in index_paths)

            original_path = os.path.join(self.monitor.ORIGINAL_DIR, f"{file_title}.json")
            if not os.path.exists(original_path):
                original_path = os.path.join(self.monitor.ORIGINAL_DIR, f"{file_title}.md")
            result["original_exists"] = os.path.exists(original_path)

            if result["index_exists"]:
                chunks = self.retriever.get_all_chunks(file_title)
                result["chunks_exist"] = len(chunks) > 0

                for chunk in chunks:
                    chunk_valid = all(key in chunk for key in ["chunk_index", "total_chunks", "data"])
                    result["chunks_valid"].append({"chunk_index": chunk.get("chunk_index"), "valid": chunk_valid})

                chunks_ok = result["chunks_exist"] and all(item["valid"] for item in result["chunks_valid"])
                # Small knowledge files are intentionally not split; in that case,
                # index + original JSON/MD existence is enough for integrity.
                result["success"] = result["index_exists"] and (chunks_ok or result["original_exists"])

            # 接入审核：将验证结果包装后执行审核
            audit_input = {
                "total_files": 1,
                "verified": 1 if result["success"] else 0,
                "failed": 0 if result["success"] else 1,
                "file_results": [
                    {
                        "file_name": f"{file_title}.json",
                        "passed": result["success"],
                        "error": result.get("error", ""),
                        "index_exists": result["index_exists"],
                        "chunks_exist": result["chunks_exist"],
                    }
                ],
                "errors": [result.get("error", "")] if not result["success"] and result.get("error") else [],
            }
            self._audit_verification_result(audit_input)

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def validate_file(
        self,
        file_title: str,
        keyword: str | Iterable[str] = "",
        expected_rule_ids: Iterable[str] | None = None,
        strict_rules: bool = False,
    ) -> Dict:
        """Validate local KB availability through registry, index, content, and retrieval."""
        result = {
            "success": False,
            "file_title": file_title,
            "registered": False,
            "original_exists": False,
            "index_exists": False,
            "content_loaded": False,
            "retrieval_hit": False,
            "matched_rule_ids": [],
            "keyword_results": [],
            "expected_rule_ids": [],
            "missing_expected_rule_ids": [],
            "rule_contract": None,
            "error": "",
        }

        try:
            registry = MetadataManager().load_registry()
            if registry is None:
                MetadataManager().scan_and_register_all()
                registry = MetadataManager().load_registry()

            file_id = file_title.replace(" ", "_").lower()
            file_info = (registry or {}).get("files", {}).get(file_id)
            result["registered"] = bool(file_info)

            original_path = os.path.join(self.monitor.ORIGINAL_DIR, f"{file_title}.json")
            if not os.path.exists(original_path):
                original_path = os.path.join(self.monitor.ORIGINAL_DIR, f"{file_title}.md")
            result["original_exists"] = os.path.exists(original_path)

            index_file = f"{file_title}_index.json"
            index_paths = [
                os.path.join(self.monitor.INDEX_DIR, "files", index_file),
                os.path.join(self.monitor.INDEX_DIR, index_file),
            ]
            result["index_exists"] = any(os.path.exists(path) for path in index_paths)

            content = self.retriever.load_aggregated_data(file_title)
            result["content_loaded"] = bool(content)

            keywords = [keyword] if isinstance(keyword, str) else list(keyword or [])
            keywords = [item.strip() for item in keywords if isinstance(item, str) and item.strip()]
            expected_ids = [
                item.strip() for item in (expected_rule_ids or []) if isinstance(item, str) and item.strip()
            ]
            result["expected_rule_ids"] = expected_ids
            all_hits = []
            if keywords:
                for search_keyword in keywords:
                    matches = self.retriever.search_business_rules(search_keyword)
                    hits = [item for item in matches if item.get("file_id") == file_id]
                    api_hit = bool(hits)
                    fallback_hit = False
                    if not api_hit and isinstance(content, dict):
                        fallback_hit = search_keyword.lower() in content.get("raw_markdown", "").lower()
                    all_hits.extend(hits)
                    result["keyword_results"].append(
                        {
                            "keyword": search_keyword,
                            "retrieval_hit": api_hit or fallback_hit,
                            "matched_rule_ids": [item.get("rule_id", item.get("id", "")) for item in hits],
                        }
                    )
                result["retrieval_hit"] = all(item["retrieval_hit"] for item in result["keyword_results"])
                result["matched_rule_ids"] = list(
                    dict.fromkeys(
                        item.get("rule_id", item.get("id", ""))
                        for item in all_hits
                        if item.get("rule_id", item.get("id", ""))
                    )
                )
            else:
                result["retrieval_hit"] = True

            matched_ids = set(result["matched_rule_ids"])
            result["missing_expected_rule_ids"] = [rule_id for rule_id in expected_ids if rule_id not in matched_ids]
            if strict_rules and original_path.lower().endswith(".json"):
                result["rule_contract"] = self.validate_rule_contract_file(original_path, strict=True)
            elif original_path.lower().endswith(".json"):
                result["rule_contract"] = self.validate_rule_contract_file(original_path, strict=False)

            result["success"] = all(
                [
                    result["registered"],
                    result["original_exists"],
                    result["index_exists"],
                    result["content_loaded"],
                    result["retrieval_hit"],
                    not result["missing_expected_rule_ids"],
                    result["rule_contract"] is None or result["rule_contract"]["success"],
                ]
            )
            return result
        except Exception as e:
            result["error"] = str(e)
            return result

    def lint_file(self, file_path: str) -> Dict:
        """Scan a knowledge source for common sensitive tokens before local KB import."""
        result = {"success": False, "file_path": file_path, "warnings": [], "errors": []}
        if not os.path.exists(file_path):
            result["errors"].append(f"file not found: {file_path}")
            return result

        try:
            with open(file_path, encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            result["errors"].append(str(e))
            return result

        sensitive_patterns = [
            "password",
            "passwd",
            "token",
            "cookie",
            "authorization",
            "secret",
            "BEGIN PRIVATE KEY",
            "DATABASE_URL",
            "手机号",
            "邮箱",
            "身份证",
            "客户地址",
            "生产环境账号",
        ]

        lowered = text.lower()
        for pattern in sensitive_patterns:
            haystack = lowered if pattern.isascii() else text
            needle = pattern.lower() if pattern.isascii() else pattern
            if needle in haystack:
                result["warnings"].append(pattern)

        if file_path.lower().endswith(".json"):
            try:
                json.loads(text)
            except Exception as e:
                result["errors"].append(f"invalid json: {e}")

        result["success"] = not result["errors"] and not result["warnings"]
        return result

    def migrate_file(self, source_path: str, target_title: str = None) -> Dict:
        """迁移单个文件到知识库

        Args:
            source_path: 源文件路径
            target_title: 目标文件标题（可选）

        Returns:
            迁移结果
        """
        import shutil
        import tempfile

        result = {"success": False, "source_path": source_path, "target_path": "", "processed": None, "error": ""}
        previous_target = None
        previous_backup = None
        process_result: Dict = {}

        try:
            if not os.path.exists(source_path):
                result["error"] = f"源文件不存在: {source_path}"
                return result

            if target_title is None:
                target_title = os.path.splitext(os.path.basename(source_path))[0]

            source_ext = os.path.splitext(source_path)[1].lower()
            if source_ext not in {".json", ".md"}:
                result["error"] = f"不支持的知识库文件类型: {source_ext or '(无扩展名)'}"
                return result
            # New structured knowledge must be queryable by stable rule id and
            # declared business keywords before it enters the local KB.  Legacy
            # files are not revalidated merely because they already exist.
            contract = self.validate_rule_contract_file(source_path, strict=True)
            result["rule_contract"] = contract
            if not contract["success"]:
                result["error"] = "rule contract validation failed"
                return result
            target_filename = f"{target_title}{source_ext}"
            target_path = os.path.join(self.monitor.ORIGINAL_DIR, target_filename)

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            if os.path.exists(target_path):
                previous_target = target_path
                fd, previous_backup = tempfile.mkstemp(prefix="kb-migrate-", suffix=source_ext)
                os.close(fd)
                shutil.copy2(target_path, previous_backup)
            shutil.copy2(source_path, target_path)
            result["target_path"] = target_path

            # Registration precedes processing so a small original is eligible
            # for logical-document inverted indexing in the same migration.
            registry_result = MetadataManager().scan_and_register_all()
            result["registry"] = registry_result
            if registry_result.get("success"):
                process_result = self.process_file(target_path)
                result["processed"] = process_result
                result["success"] = process_result["success"]
            else:
                result["error"] = registry_result.get("error", "注册表更新失败")
            if not result["success"]:
                if previous_backup:
                    shutil.copy2(previous_backup, previous_target)
                elif os.path.exists(target_path):
                    os.unlink(target_path)
                # The source rollback changes the set of registered originals;
                # regenerate metadata and derived indexes to match that state.
                result["rollback_registry"] = MetadataManager().scan_and_register_all()
                if result["rollback_registry"].get("success"):
                    result["rollback_secondary_indexes"] = self._sync_secondary_indexes()

            # 接入审核：迁移完成后执行审核
            audit_input = {
                "total_files": 1,
                "verified": 1 if result["success"] else 0,
                "failed": 0 if result["success"] else 1,
                "file_results": [
                    {
                        "file_name": target_filename,
                        "passed": result["success"],
                        "error": result.get("error", ""),
                        "split_success": process_result.get("split", {}).get("success", False),
                        "index_success": process_result.get("index", {}).get("success", False),
                    }
                ],
                "errors": [result.get("error", "")] if not result["success"] and result.get("error") else [],
            }
            self._audit_verification_result(audit_input)

            return result

        except Exception as e:
            if previous_backup and previous_target:
                shutil.copy2(previous_backup, previous_target)
            elif result.get("target_path") and os.path.exists(result["target_path"]):
                os.unlink(result["target_path"])
            result["error"] = str(e)
            return result
        finally:
            if previous_backup and os.path.exists(previous_backup):
                os.unlink(previous_backup)

    def _audit_verification_result(self, verification_result: dict) -> bool:
        """将完整性验证结果包装为统一 AuditResult 并执行审核

        Args:
            verification_result: 完整性验证结果

        Returns:
            bool: 审核是否通过
        """
        if os.getenv("KB_AUDIT_ENABLED") != "1":
            return True

        try:
            from modules.trae_test.orchestrator.audit_gateway import AuditGateway
        except Exception as e:
            logger.warning("Skip KB audit: audit gateway unavailable: %s", e)
            return True

        # 构造审核目标数据
        audit_target = {
            "verification_type": "knowledge_base",
            "total_files": verification_result.get("total_files", 0),
            "verified_files": verification_result.get("verified", 0),
            "failed_files": verification_result.get("failed", 0),
            "file_results": [
                {
                    "file_name": fr.get("file_name", "unknown"),
                    "passed": fr.get("passed", False),
                    "error": fr.get("error", ""),
                    "chunk_count": fr.get("details", {}).get("chunk_count", 0),
                    "hash_match": fr.get("details", {}).get("hash_match", False),
                }
                for fr in verification_result.get("file_results", [])
            ],
            "errors": [
                fr.get("error", "") for fr in verification_result.get("file_results", []) if not fr.get("passed", True)
            ],
        }

        try:
            gateway = AuditGateway()
            context = {"block_on_fail": False, "source": "kb_update"}
            result = gateway.audit(audit_target, "environment", context)
        except Exception as e:
            logger.warning("Skip KB audit: audit execution failed: %s", e)
            return True

        if not result.passed:
            logger.error(f"知识库完整性验证审核未通过: {result.errors}")
            return False
        logger.info("知识库完整性验证审核已通过")
        return True

    def scan_all(self) -> Dict:
        """扫描所有文件

        Returns:
            扫描结果
        """
        return self.monitor.scan_all_files()

    def process_all(self) -> Dict:
        """处理所有需要处理的文件

        Returns:
            处理结果
        """
        return self.monitor.process_all_files()

    @staticmethod
    def _normalize_duplicate_text(value: Any) -> str:
        """Normalize text for deterministic duplicate comparisons only.

        This deliberately does not infer business equivalence: Unicode form,
        case and whitespace are the only differences ignored.
        """
        if not isinstance(value, str):
            return ""
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())

    def _registered_file_records(self) -> list[dict[str, str]]:
        """Return registered files through the public retriever API.

        The governance commands must not bypass ``KnowledgeRetriever`` to read
        raw knowledge sources.  A global index supplies titles where available;
        registry-only entries remain visible with their file id as a fallback.
        """
        index = self.retriever.get_index() or {}
        indexed = {
            item.get("file_id"): item
            for item in index.get("files", [])
            if isinstance(item, dict) and isinstance(item.get("file_id"), str)
        }
        records = []
        for file_id in sorted(set(self.retriever.list_available_files() or [])):
            item = indexed.get(file_id, {})
            records.append({"file_id": file_id, "title": item.get("title") or file_id})
        return records

    def health_check(self) -> Dict:
        """Return a read-only knowledge-base health report.

        No registry, index, source file, or derived artifact is changed.
        """
        scan = self.scan_all()
        index = self.retriever.get_index() or {}
        index_status = index.get("index_status", {}) if isinstance(index, dict) else {}
        files = self._registered_file_records()
        errors = list(scan.get("errors", []))
        if index_status and not index_status.get("valid", False):
            errors.append({"component": "global_index", "error": "registry/index mismatch"})
        return {
            "success": not errors,
            "read_only": True,
            "registered_file_count": len(files),
            "scan": scan,
            "index_status": index_status,
            "errors": errors,
        }

    def dedupe_report(self, similarity_threshold: float = 0.80) -> Dict:
        """Report duplicate candidates without changing any knowledge content.

        Exact findings are based on normalized title, rule id, and SHA-256 of
        normalized rule content.  Similarity candidates are lexical character
        bigram Jaccard scores only; they are explicitly advisory and never
        imply that two ERP rules are semantically equivalent.
        """
        records = self._registered_file_records()
        title_groups: dict[str, list[dict[str, str]]] = {}
        rule_id_groups: dict[str, list[dict[str, str]]] = {}
        content_groups: dict[str, list[dict[str, str]]] = {}
        rules: list[dict[str, str]] = []
        unreadable: list[dict[str, str]] = []

        for record in records:
            title_key = self._normalize_duplicate_text(record["title"])
            if title_key:
                title_groups.setdefault(title_key, []).append(record)
            try:
                document = self.retriever.load_aggregated_data(record["title"])
            except Exception as exc:
                unreadable.append({"file_id": record["file_id"], "error": str(exc)})
                continue
            if not isinstance(document, dict):
                continue
            for rule in document.get("business_rules", []):
                if not isinstance(rule, dict):
                    continue
                rule_id = rule.get("rule_id")
                content = rule.get("content")
                if not isinstance(rule_id, str) or not rule_id.strip():
                    continue
                entry = {
                    "file_id": record["file_id"],
                    "file_title": record["title"],
                    "rule_id": rule_id.strip(),
                    "content": content if isinstance(content, str) else "",
                }
                rules.append(entry)
                rule_id_groups.setdefault(entry["rule_id"], []).append(entry)
                normalized_content = self._normalize_duplicate_text(entry["content"])
                if normalized_content:
                    fingerprint = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
                    content_groups.setdefault(fingerprint, []).append(entry)

        def duplicates(groups: dict[str, list[dict[str, str]]], kind: str) -> list[dict[str, Any]]:
            findings = []
            for key, entries in sorted(groups.items()):
                file_ids = sorted({entry["file_id"] for entry in entries})
                if len(file_ids) > 1:
                    public_entries = [
                        {field: entry[field] for field in ("file_id", "file_title", "rule_id") if field in entry}
                        for entry in entries
                    ]
                    findings.append(
                        {
                            "type": kind,
                            "key": key,
                            "entries": sorted(
                                public_entries,
                                key=lambda item: (item["file_id"], item.get("rule_id", "")),
                            ),
                        }
                    )
            return findings

        similarity_candidates = []
        content_rules = [rule for rule in rules if self._normalize_duplicate_text(rule["content"])]
        for left_index, left in enumerate(content_rules):
            left_text = self._normalize_duplicate_text(left["content"])
            left_terms = {left_text[index : index + 2] for index in range(max(1, len(left_text) - 1))}
            for right in content_rules[left_index + 1 :]:
                if left["file_id"] == right["file_id"]:
                    continue
                right_text = self._normalize_duplicate_text(right["content"])
                if left_text == right_text:
                    continue
                right_terms = {right_text[index : index + 2] for index in range(max(1, len(right_text) - 1))}
                score = len(left_terms & right_terms) / len(left_terms | right_terms)
                if score >= similarity_threshold:
                    similarity_candidates.append(
                        {
                            "method": "character_bigram_jaccard",
                            "score": round(score, 4),
                            "left": {key: left[key] for key in ("file_id", "file_title", "rule_id")},
                            "right": {key: right[key] for key in ("file_id", "file_title", "rule_id")},
                        }
                    )

        report = {
            "success": not unreadable,
            "read_only": True,
            "similarity_threshold": similarity_threshold,
            "normalized_title_duplicates": duplicates(title_groups, "normalized_title"),
            "cross_file_rule_id_duplicates": duplicates(rule_id_groups, "rule_id"),
            "exact_content_duplicates": duplicates(content_groups, "content_fingerprint"),
            "similarity_candidates": sorted(
                similarity_candidates,
                key=lambda item: (
                    -item["score"],
                    item["left"]["file_id"],
                    item["right"]["file_id"],
                ),
            ),
            "unreadable_files": unreadable,
        }
        report["summary"] = {
            "registered_file_count": len(records),
            "structured_rule_count": len(rules),
            "normalized_title_duplicate_count": len(report["normalized_title_duplicates"]),
            "cross_file_rule_id_duplicate_count": len(report["cross_file_rule_id_duplicates"]),
            "exact_content_duplicate_count": len(report["exact_content_duplicates"]),
            "similarity_candidate_count": len(report["similarity_candidates"]),
        }
        return report


def print_list_files(result: Dict):
    """打印文件列表"""
    print("=" * 80)
    print("知识库文件列表")
    print("=" * 80)

    print("\n【原始文件】")
    if result["original"]:
        for file in result["original"]:
            print(f"  {CHECK_SIGN} {file['filename']} ({file['size_kb']} KB)")
    else:
        print("  (无)")

    print("\n【内容块】")
    if result["content"]:
        for file in result["content"]:
            print(f"  {CHECK_SIGN} {file['filename']} ({file['size_kb']} KB)")
    else:
        print("  (无)")

    print("\n【索引文件】")
    if result["index"]:
        for file in result["index"]:
            print(f"  {CHECK_SIGN} {file['filename']} ({file['size_kb']} KB)")
    else:
        print("  (无)")

    print("\n【摘要】")
    print(f"  原始文件: {result['summary']['original_count']} 个，{result['summary']['original_size_kb']} KB")
    print(f"  内容块: {result['summary']['content_count']} 个，{result['summary']['content_size_kb']} KB")
    print(f"  索引文件: {result['summary']['index_count']} 个，{result['summary']['index_size_kb']} KB")
    print(f"  知识库总占用: {result['summary']['total_size_kb']} KB")


def print_split_result(result: Dict):
    """打印分割结果"""
    print("=" * 80)
    print("文件分割结果")
    print("=" * 80)
    print(f"成功: {OK_SIGN if result['success'] else FAIL_SIGN}")
    print(f"原始文件大小: {result['file_size']} 字节 ({round(result['file_size'] / 1024, 2)} KB)")
    print(f"备份路径: {result['original_path']}")
    print(f"分割块数量: {result['chunk_count']}")

    if result["chunk_files"]:
        print("\n分割块文件:")
        for i, chunk_path in enumerate(result["chunk_files"], 1):
            print(f"  {i}. {chunk_path}")

    if result["error"]:
        print(f"\n错误: {result['error']}")


def print_index_result(result: Dict):
    """打印索引结果"""
    print("=" * 80)
    print("索引构建结果")
    print("=" * 80)
    print(f"成功: {OK_SIGN if result['success'] else FAIL_SIGN}")

    if result["success"] and result["index_data"]:
        index_data = result["index_data"]
        print(f"索引文件: {result.get('index_path', '')}")

        # 兼容新旧格式
        if "file_metadata" in index_data:
            # 旧格式
            print(f"文件标题: {index_data['file_metadata']['title']}")
            print(f"分类: {index_data['file_metadata']['classification']}")
            print(f"文件大小: {index_data['file_metadata']['file_size']} 字节")
            print(f"块数量: {index_data['file_metadata']['chunk_count']}")

            print("\n块索引详情:")
            for chunk in index_data["chunks"]:
                print(
                    f"  块 {chunk['chunk_index']}: {len(chunk['keywords'])} 个关键词, 摘要: {chunk['summary'][:50]}..."
                )
        else:
            # 新格式 (IndexBuilderV3)
            print(f"文件标题: {index_data.get('title', '')}")
            print(f"分类: {index_data.get('classification', '')}")
            print(f"文件大小: {index_data.get('file_size', 0)} 字节")
            print(f"关键词数量: {len(index_data.get('keywords', []))}")
            print(f"摘要: {index_data.get('summary', '')[:100]}...")
    else:
        print(f"错误: {result['error']}")


def print_verify_result(result: Dict):
    """打印验证结果"""
    print("=" * 80)
    print("文件验证结果")
    print("=" * 80)
    print(f"文件标题: {result['file_title']}")
    print(f"成功: {OK_SIGN if result['success'] else FAIL_SIGN}")
    print(f"索引存在: {OK_SIGN if result['index_exists'] else FAIL_SIGN}")
    if result.get("chunks_exist"):
        print(f"块存在: {OK_SIGN}")
    elif result.get("original_exists"):
        print("块存在: [SKIP] 小文件使用原始文件")
    else:
        print(f"块存在: {FAIL_SIGN}")

    if result["chunks_valid"]:
        print("\n块验证:")
        for item in result["chunks_valid"]:
            print(f"  块 {item['chunk_index']}: {OK_SIGN if item['valid'] else FAIL_SIGN}")

    if result["error"]:
        print(f"\n错误: {result['error']}")


def print_migrate_result(result: Dict):
    """打印迁移结果"""
    print("=" * 80)
    print("文件迁移结果")
    print("=" * 80)
    print(f"成功: {OK_SIGN if result['success'] else FAIL_SIGN}")
    print(f"源文件: {result['source_path']}")
    print(f"目标文件: {result['target_path']}")

    if result["processed"]:
        print("\n处理结果:")
        print(f"  分割: {OK_SIGN if result['processed']['split']['success'] else FAIL_SIGN}")
    processed = result.get("processed") or {}
    index_result = processed.get("index") or {}
    print(f"  索引: {OK_SIGN if index_result.get('success', False) else FAIL_SIGN}")

    if result["error"]:
        print(f"\n错误: {result['error']}")


def print_scan_result(result: Dict):
    """打印扫描结果"""
    print("=" * 80)
    print("知识库扫描结果")
    print("=" * 80)
    print(f"总文件数: {result['total_files']}")

    if result["needs_processing"]:
        print(f"\n需要处理 ({len(result['needs_processing'])}):")
        for item in result["needs_processing"]:
            print(f"  ! {item['file']} ({round(item['file_size'] / 1024, 2)} KB)")

    if result["already_processed"]:
        print(f"\n已处理 ({len(result['already_processed'])}):")
        for item in result["already_processed"]:
            print(f"  {CHECK_SIGN} {item['file']} ({round(item['file_size'] / 1024, 2)} KB)")

    if result["errors"]:
        print(f"\n错误 ({len(result['errors'])}):")
        for item in result["errors"]:
            print(f"  {CROSS_SIGN} {item['file']}: {item['error']}")


def print_process_all_result(result: Dict):
    """打印批量处理结果"""
    print("=" * 80)
    print("批量处理结果")
    print("=" * 80)

    if result["processed"]:
        print(f"\n成功处理 ({len(result['processed'])}):")
        for filename in result["processed"]:
            print(f"  {CHECK_SIGN} {filename}")

    if result["failed"]:
        print(f"\n处理失败 ({len(result['failed'])}):")
        for item in result["failed"]:
            print(f"  {CROSS_SIGN} {item['file']}: {item['error']}")

    if result["skipped"]:
        print(f"\n跳过 ({len(result['skipped'])}):")
        for filename in result["skipped"]:
            print(f"  - {filename}")


def print_vector_result(result: Dict):
    """打印向量同步结果"""
    print("=" * 80)
    print("RAG 向量同步结果")
    print("=" * 80)
    print(f"文件: {result.get('file_title')}")
    print(f"成功: {OK_SIGN if result.get('success') else FAIL_SIGN}")
    print(f"索引条目: {result.get('indexed', 0)}")
    if result.get("error"):
        print(f"错误: {result['error']}")


def print_validate_result(result: Dict):
    print("=" * 80)
    print("Knowledge base validation result")
    print("=" * 80)
    print(f"title: {result['file_title']}")
    print(f"success: {OK_SIGN if result['success'] else FAIL_SIGN}")
    print(f"registered: {OK_SIGN if result['registered'] else FAIL_SIGN}")
    print(f"original exists: {OK_SIGN if result['original_exists'] else FAIL_SIGN}")
    print(f"index exists: {OK_SIGN if result['index_exists'] else FAIL_SIGN}")
    print(f"content loaded: {OK_SIGN if result['content_loaded'] else FAIL_SIGN}")
    print(f"retrieval hit: {OK_SIGN if result['retrieval_hit'] else FAIL_SIGN}")
    if result["matched_rule_ids"]:
        print("matched rules:")
        for rule_id in result["matched_rule_ids"]:
            print(f"  - {rule_id}")
    for item in result.get("keyword_results", []):
        print(f"keyword {item['keyword']}: {OK_SIGN if item['retrieval_hit'] else FAIL_SIGN}")
    if result.get("missing_expected_rule_ids"):
        print("missing expected rule ids:")
        for rule_id in result["missing_expected_rule_ids"]:
            print(f"  - {rule_id}")
    contract = result.get("rule_contract")
    if contract is not None and not contract.get("success", False):
        print("rule contract errors:")
        for error in contract.get("errors", []):
            print(f"  - {error}")
    if contract is not None and contract.get("warnings"):
        print("rule contract warnings:")
        for warning in contract["warnings"]:
            print(f"  - {warning}")
    if contract is not None and contract.get("lifecycle_warnings"):
        print("lifecycle warnings:")
        for warning in contract["lifecycle_warnings"]:
            print(f"  - {warning}")
    if result["error"]:
        print(f"error: {result['error']}")


def print_lint_result(result: Dict):
    print("=" * 80)
    print("Knowledge source lint result")
    print("=" * 80)
    print(f"file: {result['file_path']}")
    print(f"success: {OK_SIGN if result['success'] else FAIL_SIGN}")
    if result["warnings"]:
        print("sensitive warnings:")
        for item in result["warnings"]:
            print(f"  - {item}")
    if result["errors"]:
        print("errors:")
        for item in result["errors"]:
            print(f"  - {item}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="知识库管理CLI工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  列出所有文件:        python kb_manager.py list
  分割文件:            python kb_manager.py split --file path/to/file.json
  构建索引:            python kb_manager.py index --file path/to/file.json
  完整处理:            python kb_manager.py process --file path/to/file.json
  验证文件:            python kb_manager.py verify --title file_title
  迁移文件:            python kb_manager.py migrate --source path/to/file.json
  扫描知识库:          python kb_manager.py scan
  批量处理:            python kb_manager.py process-all
        """,
    )

    subparsers = parser.add_subparsers(title="命令", dest="command", help="可用命令")

    # list 命令
    list_parser = subparsers.add_parser("list", help="列出所有知识库文件")

    # split 命令
    split_parser = subparsers.add_parser("split", help="分割单个文件")
    split_parser.add_argument("--file", required=True, help="要分割的文件路径")
    split_parser.add_argument("--force", action="store_true", help="强制分割（忽略阈值）")

    # index 命令
    index_parser = subparsers.add_parser("index", help="为文件构建索引")
    index_parser.add_argument("--file", required=True, help="要构建索引的文件路径")

    # process 命令
    process_parser = subparsers.add_parser("process", help="完整处理文件（分割+索引）")
    process_parser.add_argument("--file", required=True, help="要处理的文件路径")
    process_parser.add_argument("--sync-vector", action="store_true", help="同步写入 RAG 本地语义向量索引")
    process_parser.add_argument(
        "--strict-rules",
        action="store_true",
        help="Require structured rule ids, keywords, and content",
    )

    # verify 命令
    verify_parser = subparsers.add_parser("verify", help="验证文件完整性")
    verify_parser.add_argument("--title", required=True, help="文件标题（不带扩展名）")

    validate_parser = subparsers.add_parser("validate", help="Validate a KB file through registry/index/retrieval")
    validate_parser.add_argument("--title", required=True, help="Knowledge file title without extension")
    validate_parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Keyword that must retrieve this file; repeatable",
    )
    validate_parser.add_argument(
        "--expect-rule-id",
        action="append",
        default=[],
        help="Expected matched rule id; repeatable",
    )
    validate_parser.add_argument(
        "--strict-rules",
        action="store_true",
        help="Fail validation when the structured rule contract is invalid",
    )

    lint_parser = subparsers.add_parser("lint", help="Lint a knowledge source for sensitive content")
    lint_parser.add_argument("--file", required=True, help="Knowledge source file path")

    # migrate 命令
    migrate_parser = subparsers.add_parser("migrate", help="迁移文件到知识库")
    migrate_parser.add_argument("--source", required=True, help="源文件路径")
    migrate_parser.add_argument("--title", help="目标文件标题（可选）")

    # scan 命令
    scan_parser = subparsers.add_parser("scan", help="扫描知识库")

    health_parser = subparsers.add_parser("health", help="只读检查知识库健康状态")
    health_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")

    dedupe_parser = subparsers.add_parser("dedupe", help="只读报告知识库重复候选")
    dedupe_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    dedupe_parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.80,
        help="报告相似规则候选的字符二元组 Jaccard 阈值（默认 0.80）",
    )

    # process-all 命令
    process_all_parser = subparsers.add_parser("process-all", help="批量处理所有需要处理的文件")

    args = parser.parse_args()

    manager = KnowledgeBaseManager()

    exit_code = 0
    if args.command == "list":
        result = manager.list_files()
        print_list_files(result)
    elif args.command == "split":
        result = manager.split_file(args.file, args.force)
        print_split_result(result)
    elif args.command == "index":
        result = manager.index_file(args.file)
        print_index_result(result)
    elif args.command == "process":
        result = manager.process_file(args.file, sync_vector=args.sync_vector, strict_rules=args.strict_rules)
        if result.get("split"):
            print_split_result(result["split"])
        if result.get("index"):
            print_index_result(result["index"])
        if result.get("vector"):
            print_vector_result(result["vector"])
        exit_code = (
            0
            if all(
                not item or item.get("success", True)
                for item in (result.get("split"), result.get("index"), result.get("vector"))
            )
            else 1
        )
    elif args.command == "verify":
        result = manager.verify_file(args.title)
        print_verify_result(result)
    elif args.command == "validate":
        result = manager.validate_file(
            args.title,
            args.keyword,
            expected_rule_ids=args.expect_rule_id,
            strict_rules=args.strict_rules,
        )
        print_validate_result(result)
    elif args.command == "lint":
        result = manager.lint_file(args.file)
        print_lint_result(result)
    elif args.command == "migrate":
        result = manager.migrate_file(args.source, args.title)
        print_migrate_result(result)
    elif args.command == "scan":
        result = manager.scan_all()
        print_scan_result(result)
        exit_code = 0 if not result.get("errors") else 1
    elif args.command == "health":
        result = manager.health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        exit_code = 0 if result.get("success", False) else 1
    elif args.command == "dedupe":
        if not 0.0 <= args.similarity_threshold <= 1.0:
            parser.error("--similarity-threshold must be between 0 and 1")
        result = manager.dedupe_report(args.similarity_threshold)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        exit_code = 0 if result.get("success", False) else 1
    elif args.command == "process-all":
        result = manager.process_all()
        print_process_all_result(result)
        exit_code = 0 if result.get("success", False) else 1
    else:
        parser.print_help()
        exit_code = 2

    if args.command in {"split", "index", "verify", "validate", "lint", "migrate"}:
        exit_code = 0 if result.get("success", False) else 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
