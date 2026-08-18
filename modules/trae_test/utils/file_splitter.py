"""JSON文件分割工具，基于JSON结构边界进行语义分割"""

import json
import os
import re
import shutil
from typing import Any

from .hash_utils import compute_file_hash
from .path_utils import PathManager, is_chunk_filename


class JSONFileSplitter:
    """JSON文件分割器，确保每个分割块保持独立的JSON结构完整性"""

    DEFAULT_SIZE_THRESHOLD = 80 * 1024

    def __init__(self, size_threshold: int = DEFAULT_SIZE_THRESHOLD):
        """初始化文件分割器

        Args:
            size_threshold: 文件大小阈值（字节），默认为80KB
        """
        self.size_threshold = size_threshold
        PathManager.ensure_kb_directories()

    @property
    def original_dir(self):
        return PathManager.get_original_dir()

    @property
    def content_dir(self):
        return PathManager.get_chunks_dir()

    ORIGINAL_DIR = original_dir
    CONTENT_DIR = content_dir

    def _get_file_size(self, file_path: str) -> int:
        """获取文件大小（字节）

        Args:
            file_path: 文件路径

        Returns:
            文件大小（字节）
        """
        return os.path.getsize(file_path)

    def _backup_original_file(self, file_path: str) -> str:
        """备份原始文件到 ORIGINAL_DIR（若已在该目录则跳过）

        Args:
            file_path: 原始文件路径

        Returns:
            备份文件路径（同原始路径若已存在）
        """
        file_name = os.path.basename(file_path)
        backup_path = os.path.join(self.ORIGINAL_DIR, file_name)

        if os.path.normpath(os.path.abspath(file_path)) == os.path.normpath(os.path.abspath(backup_path)):
            return file_path

        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(file_path, backup_path)
        return backup_path

    def _save_chunk(self, chunk_data: dict[str, Any], file_name: str, chunk_index: int) -> str:
        """保存分割块到 content/ 目录

        Args:
            chunk_data: 块数据
            file_name: 原始文件名（不含扩展名）
            chunk_index: 块索引

        Returns:
            保存的文件路径
        """
        chunk_file_name = f"{file_name}_chunk_{chunk_index:03d}.json"
        chunk_path = os.path.join(self.CONTENT_DIR, chunk_file_name)
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, ensure_ascii=False, indent=2)
        return chunk_path

    def _validate_json(self, data: dict[str, Any]) -> bool:
        """验证数据是否为有效的JSON

        Args:
            data: 要验证的数据

        Returns:
            是否有效
        """
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            json.loads(json_str)
            return True
        except Exception:
            return False

    def _estimate_item_size(self, item: Any) -> int:
        """估算单个JSON元素的大小（字节）

        Args:
            item: JSON元素

        Returns:
            估算的大小（字节）
        """
        return len(json.dumps(item, ensure_ascii=False).encode("utf-8"))

    def _split_json_list_intelligently(self, data: list[Any], file_name: str) -> list[str]:
        """智能分割JSON列表类型的数据

        根据列表元素的语义相关性进行分组，尽量保持逻辑完整性。
        如果单个元素过大，会进行递归分割。

        Args:
            data: JSON列表数据
            file_name: 原始文件名（不含扩展名）

        Returns:
            保存的块文件路径列表
        """
        chunk_files = []
        current_chunk = []
        current_size = 0
        chunk_index = 0

        for item in data:
            item_size = self._estimate_item_size(item)

            # 如果单个元素超过阈值，尝试递归分割
            if item_size > self.size_threshold:
                # 如果当前块有内容，先保存
                if current_chunk:
                    chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
                    chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                    chunk_files.append(chunk_path)
                    current_chunk = []
                    current_size = 0
                    chunk_index += 1

                # 处理大元素
                if isinstance(item, dict):
                    # 尝试按字典键分割
                    sub_chunks = self._split_large_dict(item, f"{file_name}_item", chunk_index)
                    chunk_files.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                elif isinstance(item, list):
                    # 递归分割列表
                    sub_chunks = self._split_json_list_intelligently(item, f"{file_name}_item")
                    chunk_files.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                else:
                    # 无法分割的大元素，直接保存
                    chunk_data = {"chunk_index": chunk_index, "total_chunks": 1, "data": [item]}
                    chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                    chunk_files.append(chunk_path)
                    chunk_index += 1
                continue

            # 检查是否需要新建块
            if current_chunk and (current_size + item_size > self.size_threshold):
                chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
                chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                chunk_files.append(chunk_path)
                current_chunk = []
                current_size = 0
                chunk_index += 1

            current_chunk.append(item)
            current_size += item_size

        # 保存剩余内容
        if current_chunk:
            chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
            chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
            chunk_files.append(chunk_path)

        # 更新total_chunks
        for chunk_path in chunk_files:
            with open(chunk_path, encoding="utf-8") as f:
                chunk_data = json.load(f)
            chunk_data["total_chunks"] = len(chunk_files)
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump(chunk_data, f, ensure_ascii=False, indent=2)

        return chunk_files

    def _split_large_dict(self, data: dict[str, Any], file_name: str, start_index: int) -> list[str]:
        """分割大型字典

        Args:
            data: 大型字典数据
            file_name: 文件名（不含扩展名）
            start_index: 起始块索引

        Returns:
            保存的块文件路径列表
        """
        chunk_files = []
        keys = list(data.keys())
        current_chunk = {}
        current_size = 0
        chunk_index = start_index

        for key in keys:
            value = data[key]
            item_dict = {key: value}
            item_size = self._estimate_item_size(item_dict)

            if current_chunk and (current_size + item_size > self.size_threshold):
                chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
                chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                chunk_files.append(chunk_path)
                current_chunk = {}
                current_size = 0
                chunk_index += 1

            current_chunk[key] = value
            current_size += item_size

        if current_chunk:
            chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
            chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
            chunk_files.append(chunk_path)

        # 更新total_chunks
        total_chunks = len(chunk_files)
        for chunk_path in chunk_files:
            with open(chunk_path, encoding="utf-8") as f:
                chunk_data = json.load(f)
            chunk_data["total_chunks"] = total_chunks
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump(chunk_data, f, ensure_ascii=False, indent=2)

        return chunk_files

    def _split_json_dict_intelligently(self, data: dict[str, Any], file_name: str) -> list[str]:
        """智能分割JSON字典类型的数据

        根据字典的结构特征进行分割，优先保持逻辑相关的键值对在一起。

        Args:
            data: JSON字典数据
            file_name: 原始文件名（不含扩展名）

        Returns:
            保存的块文件路径列表
        """
        chunk_files = []
        keys = list(data.keys())
        current_chunk = {}
        current_size = 0
        chunk_index = 0

        # 尝试按逻辑分组
        logical_groups = self._group_by_logic(data)

        for group in logical_groups:
            group_dict = {k: data[k] for k in group}
            group_size = self._estimate_item_size(group_dict)

            # 如果分组过大，进行细粒度分割
            if group_size > self.size_threshold:
                for key in group:
                    value = data[key]
                    item_dict = {key: value}
                    item_size = self._estimate_item_size(item_dict)

                    # 如果单个键值对也过大
                    if item_size > self.size_threshold:
                        # 先保存当前块
                        if current_chunk:
                            chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
                            chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                            chunk_files.append(chunk_path)
                            current_chunk = {}
                            current_size = 0
                            chunk_index += 1

                        # 处理大值
                        if isinstance(value, dict):
                            sub_chunks = self._split_large_dict(value, f"{file_name}_{key}", chunk_index)
                            chunk_files.extend(sub_chunks)
                            chunk_index += len(sub_chunks)
                        elif isinstance(value, list):
                            sub_chunks = self._split_json_list_intelligently(value, f"{file_name}_{key}")
                            chunk_files.extend(sub_chunks)
                            chunk_index += len(sub_chunks)
                        else:
                            chunk_data = {"chunk_index": chunk_index, "total_chunks": 1, "data": item_dict}
                            chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                            chunk_files.append(chunk_path)
                            chunk_index += 1
                        continue

                    if current_chunk and (current_size + item_size > self.size_threshold):
                        chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
                        chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                        chunk_files.append(chunk_path)
                        current_chunk = {}
                        current_size = 0
                        chunk_index += 1

                    current_chunk[key] = value
                    current_size += item_size
            else:
                # 分组大小合适，直接添加
                if current_chunk:
                    combined_size = current_size + group_size
                    if combined_size > self.size_threshold:
                        # 先保存当前块
                        chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
                        chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
                        chunk_files.append(chunk_path)
                        current_chunk = {}
                        current_size = 0
                        chunk_index += 1

                current_chunk.update(group_dict)
                current_size += group_size

        # 保存剩余内容
        if current_chunk:
            chunk_data = {"chunk_index": chunk_index, "total_chunks": 0, "data": current_chunk}
            chunk_path = self._save_chunk(chunk_data, file_name, chunk_index)
            chunk_files.append(chunk_path)

        # 更新total_chunks
        total_chunks = len(chunk_files)
        for chunk_path in chunk_files:
            with open(chunk_path, encoding="utf-8") as f:
                chunk_data = json.load(f)
            chunk_data["total_chunks"] = total_chunks
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump(chunk_data, f, ensure_ascii=False, indent=2)

        return chunk_files

    def _group_by_logic(self, data: dict[str, Any]) -> list[list[str]]:
        """按逻辑关系对字典键进行分组

        Args:
            data: 字典数据

        Returns:
            分组后的键列表
        """
        groups = []
        processed_keys = set()

        # 定义常见的逻辑分组模式
        common_groups = [
            ["pages", "page_list", "page_info"],
            ["business_rules", "rules", "rule_list"],
            ["requirements", "req_list", "requirements_list"],
            ["fields", "field_specs", "field_definitions"],
            ["flows", "workflows", "processes"],
            ["config", "configuration", "settings"],
            ["metadata", "meta", "info"],
            ["api", "apis", "endpoints"],
        ]

        # 按常见模式分组
        for group_pattern in common_groups:
            matched_keys = [k for k in data if k in group_pattern and k not in processed_keys]
            if matched_keys:
                groups.append(matched_keys)
                processed_keys.update(matched_keys)

        # 按前缀分组剩余的键
        prefix_groups = {}
        remaining_keys = [k for k in data if k not in processed_keys]

        for key in remaining_keys:
            # 提取前缀（以下划线或大小写分隔）
            prefix = self._extract_prefix(key)
            if prefix:
                if prefix not in prefix_groups:
                    prefix_groups[prefix] = []
                prefix_groups[prefix].append(key)

        # 添加前缀分组
        for prefix, keys in prefix_groups.items():
            if len(keys) > 1:
                groups.append(keys)
                processed_keys.update(keys)

        # 剩余的单独键
        remaining = [k for k in data if k not in processed_keys]
        for key in remaining:
            groups.append([key])

        return groups

    def _extract_prefix(self, key: str) -> str | None:
        """从键名提取前缀

        Args:
            key: 键名

        Returns:
            前缀字符串，如果无法提取返回None
        """
        # 下划线分隔
        if "_" in key:
            parts = key.split("_")
            if len(parts) > 1:
                return parts[0]

        # 大小写分隔（驼峰式）
        match = re.match(r"^([a-z]+)([A-Z])", key)
        if match:
            return match.group(1)

        return None

    def split_file(self, file_path: str) -> dict[str, Any]:
        """分割JSON文件

        Args:
            file_path: 要分割的文件路径

        Returns:
            分割结果字典，包含：
                - original_path: 原始文件备份路径
                - chunk_files: 分割块文件路径列表
                - file_size: 原始文件大小
                - chunk_count: 分割块数量
                - success: 是否成功
                - error: 错误信息（如果有）
        """
        result = {
            "original_path": "",
            "chunk_files": [],
            "file_size": 0,
            "chunk_count": 0,
            "success": False,
            "error": "",
        }

        try:
            if not os.path.exists(file_path):
                result["error"] = f"文件不存在: {file_path}"
                return result

            file_name = os.path.splitext(os.path.basename(file_path))[0]
            # Remove stale chunks before rebuilding. Otherwise old chunks remain
            # when a source file shrinks or changes structure.
            if os.path.exists(self.CONTENT_DIR):
                for filename in os.listdir(self.CONTENT_DIR):
                    if filename.startswith(f"{file_name}_") and is_chunk_filename(filename):
                        os.remove(os.path.join(self.CONTENT_DIR, filename))

            file_size = self._get_file_size(file_path)
            result["file_size"] = file_size

            # Markdown knowledge sources are indexed as documents and do not
            # need JSON structural splitting. Keep the source intact.
            if os.path.splitext(file_path)[1].lower() == ".md":
                result["success"] = True
                result["chunk_count"] = 0
                result["chunk_files"] = []
                result["original_path"] = file_path
                return result

            if file_size <= self.size_threshold:
                result["success"] = True
                result["chunk_count"] = 0
                result["chunk_files"] = []
                result["original_path"] = file_path
                return result

            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            if not self._validate_json(data):
                result["error"] = "文件内容不是有效的JSON"
                return result

            backup_path = self._backup_original_file(file_path)
            result["original_path"] = backup_path

            if isinstance(data, list):
                chunk_files = self._split_json_list_intelligently(data, file_name)
            elif isinstance(data, dict):
                chunk_files = self._split_json_dict_intelligently(data, file_name)
            else:
                result["error"] = "不支持的JSON数据类型（仅支持list和dict）"
                return result

            result["chunk_files"] = chunk_files
            result["chunk_count"] = len(chunk_files)
            result["success"] = True

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def validate_chunks(self, chunk_files: list[str]) -> tuple[bool, list[str]]:
        """验证分割块是否都是有效的JSON

        Args:
            chunk_files: 块文件路径列表

        Returns:
            (是否全部有效, 错误文件列表)
        """
        invalid_files = []

        for chunk_path in chunk_files:
            try:
                with open(chunk_path, encoding="utf-8") as f:
                    chunk_data = json.load(f)

                if "chunk_index" not in chunk_data:
                    invalid_files.append(f"{chunk_path} (缺少 chunk_index)")
                    continue

                if "total_chunks" not in chunk_data:
                    invalid_files.append(f"{chunk_path} (缺少 total_chunks)")
                    continue

                if "data" not in chunk_data:
                    invalid_files.append(f"{chunk_path} (缺少 data)")
                    continue

                if not self._validate_json(chunk_data["data"]):
                    invalid_files.append(f"{chunk_path} (data 字段无效)")
                    continue

                # 验证索引连续性
                chunk_index = chunk_data["chunk_index"]
                total_chunks = chunk_data["total_chunks"]
                if chunk_index < 0 or chunk_index >= total_chunks:
                    invalid_files.append(f"{chunk_path} (chunk_index {chunk_index} 超出范围 [0, {total_chunks-1}])")

            except Exception as e:
                invalid_files.append(f"{chunk_path} ({str(e)})")

        return len(invalid_files) == 0, invalid_files

    def reconstruct_file(self, chunk_files: list[str], output_path: str) -> bool:
        """从分割块重建原始文件

        Args:
            chunk_files: 块文件路径列表（按顺序）
            output_path: 输出文件路径

        Returns:
            是否成功
        """
        try:
            # 使用更健壮的正则表达式提取数字索引和子键类型
            def get_index(path):
                basename = os.path.basename(path)
                match = re.search(r"_chunk_(\d+)\.json", basename)
                if match:
                    return int(match.group(1))
                return 0

            def get_sub_key(path):
                """提取子键类型，如 requirements_by_module, problems 等"""
                basename = os.path.basename(path)
                match = re.search(r"_(\w+)_chunk_\d+\.json", basename)
                if match and match.group(1) not in ("0",):
                    return match.group(1)
                return None

            # 分组：root chunks (无子键) 和 sub chunks (有子键)
            root_chunks = []
            sub_chunk_groups = {}

            for chunk_path in chunk_files:
                sub_key = get_sub_key(chunk_path)
                if sub_key:
                    if sub_key not in sub_chunk_groups:
                        sub_chunk_groups[sub_key] = []
                    sub_chunk_groups[sub_key].append(chunk_path)
                else:
                    root_chunks.append(chunk_path)

            root_chunks.sort(key=get_index)
            for key in sub_chunk_groups:
                sub_chunk_groups[key].sort(key=get_index)

            # Interface-document module items are split into a metadata chunk
            # and a sibling ``interfaces`` chunk. Treat both as one modules
            # group so they can be merged back into the matching module.
            if "modules" in sub_chunk_groups and "item" in sub_chunk_groups:
                item_paths = sub_chunk_groups["item"]
                if any("_modules_item_chunk_" in os.path.basename(path) for path in item_paths):
                    sub_chunk_groups["modules"].extend(item_paths)
                    sub_chunk_groups["modules"].sort(key=get_index)
                    del sub_chunk_groups["item"]

            # 有效数据键
            valid_data_keys = {
                "data",
                "_raw",
                "_formatted_content",
                "requirements_by_module",
                "modules",
                "problems",
                "learned_test_cases",
                "rules",
                "business_rules",
                "test_cases",
            }

            def extract_data(chunk_data):
                """从chunk数据中提取实际内容"""
                for key in valid_data_keys:
                    if key in chunk_data:
                        return chunk_data[key]
                # 返回整个chunk排除元数据键后的内容
                result = {}
                for k, v in chunk_data.items():
                    if k not in (
                        "chunk_index",
                        "chunk_type",
                        "file_name",
                        "created_at",
                        "original_hash",
                        "total_chunks",
                        "sub_chunks",
                        "summary",
                        "data_keys",
                    ):
                        result[k] = v
                return result if result else None

            all_data = {}
            data_type = None
            merged_lists = {}

            # 先处理 root chunks
            for chunk_path in root_chunks:
                with open(chunk_path, encoding="utf-8") as f:
                    chunk_data = json.load(f)

                data = extract_data(chunk_data)
                if data is None:
                    continue

                if isinstance(data, dict):
                    all_data.update(data)

            # 再处理 sub chunks（按组聚合）
            for sub_key, paths in sub_chunk_groups.items():
                if sub_key == "modules" and any("_modules_item_chunk_" in os.path.basename(path) for path in paths):
                    module_chunks = []
                    item_parts = []
                    for chunk_path in paths:
                        with open(chunk_path, encoding="utf-8") as f:
                            chunk_data = json.load(f)
                        data = extract_data(chunk_data)
                        if isinstance(data, list):
                            module_chunks.extend(data)
                        elif isinstance(data, dict):
                            item_parts.append(data)

                    for part in item_parts:
                        name = part.get("name")
                        if name:
                            target = next((item for item in module_chunks if item.get("name") == name), None)
                            if target is None:
                                target = {"name": name}
                                module_chunks.append(target)
                            target.update(part)
                        elif module_chunks:
                            module_chunks[-1].update(part)
                    merged_lists[sub_key] = module_chunks
                    continue

                merged = None
                for chunk_path in paths:
                    with open(chunk_path, encoding="utf-8") as f:
                        chunk_data = json.load(f)

                    data = extract_data(chunk_data)
                    if data is None:
                        continue

                    if merged is None:
                        merged = data
                    else:
                        if isinstance(merged, list) and isinstance(data, list):
                            merged.extend(data)
                        elif isinstance(merged, dict) and isinstance(data, dict):
                            merged.update(data)
                        elif isinstance(merged, list):
                            merged.append(data)

                if merged is not None:
                    merged_lists[sub_key] = merged

            # 合并所有数据
            all_data.update(merged_lists)

            # 如果 all_data 为空，尝试从 root chunk 直接提取
            if not all_data and root_chunks:
                with open(root_chunks[0], encoding="utf-8") as f:
                    chunk_data = json.load(f)
                for k, v in chunk_data.items():
                    if k not in (
                        "chunk_index",
                        "chunk_type",
                        "file_name",
                        "created_at",
                        "original_hash",
                        "total_chunks",
                        "sub_chunks",
                        "summary",
                        "data_keys",
                    ):
                        all_data[k] = v

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            print(f"重建文件错误: {str(e)}")
            import traceback

            traceback.print_exc()
            return False

    def verify_integrity(self, original_path: str, chunk_files: list[str]) -> dict[str, Any]:
        """验证分割的完整性（比较原始文件和重建文件）

        Args:
            original_path: 原始文件路径
            chunk_files: 块文件路径列表

        Returns:
            验证结果字典
        """
        import tempfile

        result = {"success": False, "original_size": 0, "reconstructed_size": 0, "hash_match": False, "error": ""}

        try:
            # 获取原始文件大小
            result["original_size"] = self._get_file_size(original_path)

            # 临时文件重建
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as temp:
                temp_path = temp.name

            if not self.reconstruct_file(chunk_files, temp_path):
                result["error"] = "重建文件失败"
                return result

            # 获取重建文件大小
            result["reconstructed_size"] = self._get_file_size(temp_path)

            # 比较内容哈希
            original_hash = self._compute_hash(original_path)
            reconstructed_hash = self._compute_hash(temp_path)
            result["hash_match"] = original_hash == reconstructed_hash

            # 清理临时文件
            os.unlink(temp_path)

            result["success"] = result["hash_match"]
            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def _compute_hash(self, file_path: str) -> str:
        """计算文件的SHA256哈希

        Args:
            file_path: 文件路径

        Returns:
            哈希字符串
        """
        return compute_file_hash(file_path)


def split_file_cli(file_path: str, size_threshold: int = None) -> dict[str, Any]:
    """命令行接口：分割文件

    Args:
        file_path: 文件路径
        size_threshold: 大小阈值（字节），可选

    Returns:
        分割结果
    """
    splitter = JSONFileSplitter(size_threshold) if size_threshold else JSONFileSplitter()
    result = splitter.split_file(file_path)

    if result["success"] and result["chunk_files"]:
        is_valid, invalid_files = splitter.validate_chunks(result["chunk_files"])
        result["validation_passed"] = is_valid
        result["invalid_files"] = invalid_files

        # 如果原始文件已备份，验证完整性
        if result["original_path"]:
            integrity_result = splitter.verify_integrity(result["original_path"], result["chunk_files"])
            result["integrity_check"] = integrity_result

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python file_splitter.py <file_path> [size_threshold]")
        print("示例: python file_splitter.py data/large_file.json 81920")
        sys.exit(1)

    file_path = sys.argv[1]
    size_threshold = int(sys.argv[2]) if len(sys.argv) > 2 else None

    result = split_file_cli(file_path, size_threshold)

    print("=" * 60)
    print("文件分割结果")
    print("=" * 60)
    print(f"成功: {'✓' if result['success'] else '✗'}")
    print(f"原始文件大小: {result['file_size']} 字节")
    print(f"备份路径: {result['original_path']}")
    print(f"分割块数量: {result['chunk_count']}")

    if result["chunk_files"]:
        print("\n分割块文件:")
        for i, chunk_path in enumerate(result["chunk_files"], 1):
            chunk_size = os.path.getsize(chunk_path)
            print(f"  {i}. {chunk_path} ({chunk_size} 字节)")

    if "validation_passed" in result:
        print(f"\n验证结果: {'✓ 通过' if result['validation_passed'] else '✗ 失败'}")
        if not result["validation_passed"] and result["invalid_files"]:
            print("无效文件:")
            for invalid_file in result["invalid_files"]:
                print(f"  - {invalid_file}")

    if "integrity_check" in result:
        check = result["integrity_check"]
        print(f"\n完整性检查: {'✓ 通过' if check['success'] else '✗ 失败'}")
        if check["success"]:
            print(f"  原始文件大小: {check['original_size']} 字节")
            print(f"  重建文件大小: {check['reconstructed_size']} 字节")
            print(f"  哈希匹配: {'✓' if check['hash_match'] else '✗'}")

    if result["error"]:
        print(f"\n错误: {result['error']}")
        sys.exit(1)

    print("\n✓ 分割完成！")
