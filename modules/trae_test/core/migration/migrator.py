from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from modules.trae_test.core.db_pool import get_session
from modules.trae_test.core.migration.schema import (
    KBBusinessRule,
    KBChunk,
    KBFile,
    KBProblem,
    KBRequirement,
    KBTestCase,
)

ORIGINAL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "assets", "knowledge_base", "data", "original"
)
ORIGINAL_DIR = os.path.abspath(ORIGINAL_DIR)

CHUNKS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "assets", "knowledge_base", "data", "chunks"
)
CHUNKS_DIR = os.path.abspath(CHUNKS_DIR)

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "assets", "knowledge_base", "metadata", "file_registry.json"
)
REGISTRY_PATH = os.path.abspath(REGISTRY_PATH)


def _compute_sha256(file_path: str) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _load_registry() -> dict:
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}}


def _read_file_content(file_path: str) -> dict | None:
    try:
        with open(file_path, encoding="utf-8") as f:
            raw = f.read()
            if not raw.strip():
                return {}
            return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_items(content: dict, keys: list[str]) -> list[dict]:
    for key in keys:
        if key in content and isinstance(content[key], list):
            return content[key]
    for key in content:
        if isinstance(content[key], list) and len(content[key]) > 0 and isinstance(content[key][0], (dict, str)):
            for inner_key in keys:
                if key.lower() in inner_key.lower() or inner_key.lower() in key.lower():
                    return content[key]
    return []


def _normalize_item(item: Any) -> dict:
    if isinstance(item, str):
        return {"value": item}
    if isinstance(item, dict):
        return item
    return {"value": str(item)}


def migrate_file(file_name: str) -> dict:
    file_path = os.path.join(ORIGINAL_DIR, file_name)
    result = {
        "file": file_name,
        "success": False,
        "phases": {},
        "error": "",
    }

    if not os.path.exists(file_path):
        result["error"] = f"文件不存在: {file_path}"
        return result

    if not file_name.lower().endswith(".json"):
        result["error"] = "仅支持 JSON 文件迁移"
        return result

    title = os.path.splitext(file_name)[0]

    registry = _load_registry()
    file_info = registry.get("files", {}).get(title.lower().replace(" ", "_"))
    tags = file_info.get("tags", []) if file_info else []
    classification = file_info.get("classification", "") if file_info else ""

    file_hash = _compute_sha256(file_path)
    file_size = os.path.getsize(file_path)

    session = get_session()
    try:
        existing = session.query(KBFile).filter(KBFile.original_hash == file_hash).first()
        if existing is not None:
            result["success"] = True
            result["phases"]["skipped"] = "hash 已存在，跳过"
            session.close()
            return result

        kb_file = KBFile(
            title=title,
            file_id=title.lower().replace(" ", "_"),
            original_path=f"data/original/{file_name}",
            tags=tags,
            classification=classification,
            original_hash=file_hash,
            total_size=file_size,
            chunk_count=0,
        )
        session.add(kb_file)
        session.flush()
        result["phases"]["file"] = "ok"

        content = _read_file_content(file_path)
        if content is None:
            session.rollback()
            result["error"] = "无法解析 JSON 内容"
            session.close()
            return result

        requirements = _extract_items(content, ["requirements", "需求", "requirement_list", "需求清单"])
        req_count = 0
        for item in requirements:
            norm = _normalize_item(item)
            kb_req = KBRequirement(
                file_id=kb_file.id,
                module=norm.get("module", classification),
                requirement_id=norm.get("id", norm.get("requirement_id", "")),
                title=norm.get("title", norm.get("name", norm.get("value", ""))),
                description=norm.get("description", norm.get("desc", "")),
                priority=norm.get("priority", ""),
                status=norm.get("status", ""),
                data=norm,
            )
            session.add(kb_req)
            req_count += 1
        result["phases"]["requirements"] = req_count

        rules = _extract_items(content, ["business_rules", "rules", "validations", "业务规则", "validation_rules"])
        rule_count = 0
        for item in rules:
            norm = _normalize_item(item)
            kb_rule = KBBusinessRule(
                file_id=kb_file.id,
                module=norm.get("module", classification),
                rule_name=norm.get("name", norm.get("rule_name", norm.get("title", ""))),
                rule_content=norm.get("content", norm.get("rule", norm.get("description", ""))),
                data=norm,
            )
            session.add(kb_rule)
            rule_count += 1
        result["phases"]["business_rules"] = rule_count

        problems = _extract_items(content, ["problems", "线上问题", "issues", "缺陷"])
        prob_count = 0
        for item in problems:
            norm = _normalize_item(item)
            kb_prob = KBProblem(
                file_id=kb_file.id,
                module=norm.get("module", classification),
                problem_title=norm.get("title", norm.get("problem", norm.get("value", ""))),
                problem_description=norm.get("description", norm.get("detail", "")),
                severity=norm.get("severity", norm.get("level", "")),
                status=norm.get("status", ""),
                data=norm,
            )
            session.add(kb_prob)
            prob_count += 1
        result["phases"]["problems"] = prob_count

        test_cases = _extract_items(content, ["test_cases", "测试用例", "cases", "learned_test_cases"])
        tc_count = 0
        for item in test_cases:
            norm = _normalize_item(item)
            kb_tc = KBTestCase(
                file_id=kb_file.id,
                module=norm.get("module", classification),
                case_title=norm.get("title", norm.get("case_title", norm.get("value", ""))),
                case_description=norm.get("description", norm.get("steps", "")),
                priority=norm.get("priority", ""),
                data=norm,
            )
            session.add(kb_tc)
            tc_count += 1
        result["phases"]["test_cases"] = tc_count

        session.commit()
        result["success"] = True

    except Exception as e:
        session.rollback()
        result["error"] = str(e)
    finally:
        session.close()

    return result


def migrate_chunks(file_name: str) -> dict:
    file_path = os.path.join(ORIGINAL_DIR, file_name)
    title = os.path.splitext(file_name)[0]
    result = {"file": file_name, "success": False, "chunk_count": 0, "error": ""}

    if not os.path.exists(file_path):
        result["error"] = f"文件不存在: {file_path}"
        return result

    file_hash = _compute_sha256(file_path)
    content = _read_file_content(file_path)

    session = get_session()
    try:
        kb_file = session.query(KBFile).filter(KBFile.original_hash == file_hash).first()
        if kb_file is None:
            result["error"] = "文件尚未迁移，请先执行 migrate_file"
            session.close()
            return result

        session.query(KBChunk).filter(KBChunk.file_id == kb_file.id).delete()

        chunk_count = 0
        if content is not None:
            content_str = json.dumps(content, ensure_ascii=False)
            if len(content_str) > 40000:
                if isinstance(content, dict):
                    buffer = {}
                    buf_size = 0
                    for key, value in content.items():
                        entry = json.dumps({key: value}, ensure_ascii=False)
                        if buf_size + len(entry) > 40000 and buffer:
                            chunk = KBChunk(
                                file_id=kb_file.id,
                                chunk_index=chunk_count,
                                content=buffer,
                                summary=f"{title} 分块 {chunk_count + 1}",
                                keywords=list(buffer.keys()),
                            )
                            session.add(chunk)
                            chunk_count += 1
                            buffer = {}
                            buf_size = 0
                        buffer[key] = value
                        buf_size += len(entry)
                    if buffer:
                        chunk = KBChunk(
                            file_id=kb_file.id,
                            chunk_index=chunk_count,
                            content=buffer,
                            summary=f"{title} 分块 {chunk_count + 1}",
                            keywords=list(buffer.keys()),
                        )
                        session.add(chunk)
                        chunk_count += 1
                else:
                    chunk = KBChunk(
                        file_id=kb_file.id,
                        chunk_index=0,
                        content={"data": content},
                        summary=title,
                    )
                    session.add(chunk)
                    chunk_count = 1
            else:
                chunk = KBChunk(
                    file_id=kb_file.id,
                    chunk_index=0,
                    content=content if isinstance(content, dict) else {"data": content},
                    summary=title,
                )
                session.add(chunk)
                chunk_count = 1

        kb_file.chunk_count = chunk_count
        session.commit()
        result["success"] = True
        result["chunk_count"] = chunk_count

    except Exception as e:
        session.rollback()
        result["error"] = str(e)
    finally:
        session.close()

    return result


def migrate_all() -> dict:
    result = {"success": True, "total": 0, "migrated": 0, "skipped": 0, "failed": 0, "details": []}

    if not os.path.exists(ORIGINAL_DIR):
        result["success"] = False
        result["error"] = f"原始目录不存在: {ORIGINAL_DIR}"
        return result

    json_files = sorted(f for f in os.listdir(ORIGINAL_DIR) if f.lower().endswith(".json"))
    result["total"] = len(json_files)

    for fname in json_files:
        detail = migrate_file(fname)
        result["details"].append(detail)
        if detail["success"]:
            if detail["phases"].get("skipped"):
                result["skipped"] += 1
            else:
                result["migrated"] += 1
            chunk_result = migrate_chunks(fname)
            detail["phases"]["chunks"] = chunk_result
        else:
            result["failed"] += 1

    if result["failed"] > 0:
        result["success"] = False

    return result


def verify_all() -> dict:
    result = {"success": True, "total": 0, "matched": 0, "mismatched": 0, "details": []}

    if not os.path.exists(ORIGINAL_DIR):
        result["success"] = False
        result["error"] = "原始目录不存在"
        return result

    session = get_session()
    try:
        all_files = session.query(KBFile).all()
        db_hashes = {f.original_hash: f.title for f in all_files}

        json_files = sorted(f for f in os.listdir(ORIGINAL_DIR) if f.lower().endswith(".json"))
        result["total"] = len(json_files)

        for fname in json_files:
            file_path = os.path.join(ORIGINAL_DIR, fname)
            actual_hash = _compute_sha256(file_path)
            title = os.path.splitext(fname)[0]

            matched = actual_hash in db_hashes
            detail = {
                "file": fname,
                "hash": actual_hash,
                "in_db": matched,
            }
            result["details"].append(detail)

            if matched:
                result["matched"] += 1
            else:
                result["mismatched"] += 1

        if result["mismatched"] > 0:
            result["success"] = False

        result["db_records"] = {
            "kb_files": session.query(KBFile).count(),
            "kb_requirements": session.query(KBRequirement).count(),
            "kb_business_rules": session.query(KBBusinessRule).count(),
            "kb_problems": session.query(KBProblem).count(),
            "kb_test_cases": session.query(KBTestCase).count(),
        }

    finally:
        session.close()

    return result
