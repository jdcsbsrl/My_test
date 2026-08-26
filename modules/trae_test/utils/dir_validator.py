"""用例目录合法性校验

强制用例目录字段格式为 '一级 - 二级 - 三级'（空格-连字符-空格），
且一/二/三级必须严格出现在 `assets/knowledge_base/导航规范/ERP菜单导航与路由.json`
的 `module_hierarchy` 中。

这是对知识库铁律的守护：杜绝手动脑补目录名导致的用例数据偏差。

v2 新增：
  - fix_directory() 自动修复常见格式问题（分隔符、多余后缀等）
  - validate_directory(strict=False) 宽容模式，校验失败不阻断而是返回警告
  - find_closest_directory() 模糊匹配，为不合规目录找到最接近的合规目录
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_SEPARATOR = " - "
_LOOSE_SEPARATORS = re.compile(r"\s*[-\u2013\u2014]\s*")


def _nav_json_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(
            here,
            "..",
            "..",
            "..",
            "assets",
            "knowledge_base",
            "data",
            "original",
            "ERP菜单导航与路由.json",
        )
    )


def _fallback_nav_json_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", "fixtures", "navigation", "module_hierarchy.json"))


@lru_cache(maxsize=1)
def _load_module_hierarchy() -> dict[str, dict[str, list[str]]]:
    path = _nav_json_path()
    if not os.path.exists(path):
        path = _fallback_nav_json_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("module_hierarchy", {}) or {}


def list_allowed_top_levels() -> list[str]:
    return list(_load_module_hierarchy().keys())


def _strip_suffix(text: str) -> str:
    for suffix in ("模块", "管理", "类", "中心", "设置", "列表", "页面"):
        if text.endswith(suffix) and len(text) > len(suffix):
            stripped = text[: -len(suffix)]
            return stripped
    return text


def find_closest_directory(directory: str) -> str | None:
    hierarchy = _load_module_hierarchy()
    if not hierarchy:
        return None

    parts = _LOOSE_SEPARATORS.split(directory.strip())
    if len(parts) != 3:
        if len(parts) == 1:
            parts = re.split(r"[\\\/]", directory.strip())
        if len(parts) != 3:
            return None

    raw_top, raw_second, raw_third = (p.strip() for p in parts)
    if not raw_top or not raw_second or not raw_third:
        return None

    top = None
    for key in hierarchy.keys():
        if (
            key == raw_top
            or _strip_suffix(key) == _strip_suffix(raw_top)
            or key.startswith(raw_top)
            or raw_top.startswith(key)
        ):
            top = key
            break
    if top is None:
        for key in hierarchy.keys():
            if raw_top in key or key in raw_top:
                top = key
                break
    if top is None:
        return None

    second_map = hierarchy.get(top, {}) or {}
    second = None
    for key in second_map.keys():
        if (
            key == raw_second
            or _strip_suffix(key) == _strip_suffix(raw_second)
            or key.startswith(raw_second)
            or raw_second.startswith(key)
        ):
            second = key
            break
    if second is None:
        for key in second_map.keys():
            if raw_second in key or key in raw_second:
                second = key
                break
    if second is None:
        return None

    third_list = second_map.get(second, []) or []
    third = None
    for item in third_list:
        if (
            item == raw_third
            or _strip_suffix(item) == _strip_suffix(raw_third)
            or item.startswith(raw_third)
            or raw_third.startswith(item)
        ):
            third = item
            break
    if third is None:
        for item in third_list:
            if raw_third in item or item in raw_third:
                third = item
                break
    if third is None:
        return None

    return f"{top} - {second} - {third}"


def fix_directory(directory: str) -> tuple[str, list[str]]:
    fixes: list[str] = []
    text = str(directory).strip()

    if not text:
        return text, fixes

    if _SEPARATOR not in text:
        parts = _LOOSE_SEPARATORS.split(text)
        if len(parts) == 3:
            text = f"{parts[0].strip()} - {parts[1].strip()} - {parts[2].strip()}"
            fixes.append(f"分隔符修复：'{directory}' -> '{text}'")

    ok, _ = validate_directory(text, strict=True)
    if ok:
        return text, fixes

    closest = find_closest_directory(text)
    if closest:
        fixes.append(f"模糊匹配修复：'{text}' -> '{closest}'")
        return closest, fixes

    return text, fixes


def validate_directory(directory: str, strict: bool = True) -> tuple[bool, str]:
    if directory is None:
        msg = "用例目录不能为空（None）"
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    text = str(directory).strip()
    if not text:
        msg = "用例目录不能为空字符串"
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    parts = text.split(_SEPARATOR)
    if len(parts) != 3:
        msg = (
            f"用例目录必须是 3 级，并用 '{_SEPARATOR}'（空格+连字符+空格）分隔；" f"实际得到 {len(parts)} 级：{text!r}"
        )
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    top, second, third = (p.strip() for p in parts)
    if not top or not second or not third:
        msg = f"用例目录的每一级都不能为空：{text!r}"
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    hierarchy = _load_module_hierarchy()

    if top not in hierarchy:
        allowed = "/".join(list_allowed_top_levels())
        msg = f"一级目录 {top!r} 不在 module_hierarchy 中（合法值：{allowed}）"
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    second_map = hierarchy.get(top, {}) or {}
    if second not in second_map:
        allowed = "/".join(second_map.keys())
        msg = f"二级目录 {second!r} 不在 module_hierarchy[{top!r}] 中" f"（合法值：{allowed}）"
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    third_list = second_map.get(second, []) or []
    if third not in third_list:
        allowed = "/".join(third_list)
        msg = f"三级页面 {third!r} 不在 module_hierarchy[{top!r}][{second!r}] 中" f"（合法值：{allowed}）"
        return (False, msg) if strict else (True, f"[WARN] {msg}")

    return True, ""


def assert_directory(directory: str) -> None:
    ok, err = validate_directory(directory, strict=True)
    if not ok:
        raise ValueError(f"用例目录不合规：{err}")
