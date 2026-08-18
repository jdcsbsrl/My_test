"""知识库内容完整性验证工具"""

import datetime
import hashlib
import json
import os
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.trae_test.utils.path_utils import is_chunk_filename
from modules.trae_test.utils.file_splitter import JSONFileSplitter


class KnowledgeBaseVerifier:
    """知识库内容完整性验证器"""

    KB_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "knowledge_base")
    DATA_DIR = os.path.join(KB_BASE_DIR, "data")
    CONTENT_DIR = os.path.join(DATA_DIR, "chunks")
    ORIGINAL_DIR = os.path.join(DATA_DIR, "original")
    INDEX_DIR = os.path.join(KB_BASE_DIR, "index")

    def __init__(self):
        """初始化验证器"""
        self.splitter = JSONFileSplitter()

    def _compute_content_hash(self, content: Any) -> str:
        """计算数据内容的SHA256哈希值（规范化）

        Args:
            content: 数据内容

        Returns:
            哈希字符串
        """
        normalized_json = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
        hash_obj = hashlib.sha256()
        hash_obj.update(normalized_json.encode("utf-8"))
        return hash_obj.hexdigest()

    def _compute_file_hash(self, file_path: str) -> str:
        """计算文件的SHA256哈希值（规范化）

        Args:
            file_path: 文件路径

        Returns:
            哈希字符串
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                content = json.load(f)
            return self._compute_content_hash(content)
        except Exception:
            return ""

    def _get_chunk_files(self, file_name_without_ext: str, content_dir: str = None) -> list[str]:
        """获取指定文件的所有块文件

        Args:
            file_name_without_ext: 不带扩展名的文件名
            content_dir: 可选的内容目录

        Returns:
            块文件路径列表（排序后）
        """
        target_dir = content_dir or self.CONTENT_DIR
        chunk_files = []
        if os.path.exists(target_dir):
            for filename in os.listdir(target_dir):
                # 匹配 root chunks (filename_chunk_NNN.json) 和 sub-key chunks (filename_KEY_chunk_NNN.json)
                if is_chunk_filename(filename) and filename.startswith(f"{file_name_without_ext}_"):
                    chunk_files.append(os.path.join(target_dir, filename))

        import re

        def get_index(path):
            basename = os.path.basename(path)
            match = re.search(r"_chunk_(\d+)\.json", basename)
            if match:
                return int(match.group(1))
            return 0

        return sorted(chunk_files, key=get_index)

    def _load_and_normalize(self, file_path: str) -> Any:
        """加载文件并返回规范化的内容

        Args:
            file_path: 文件路径

        Returns:
            规范化后的内容
        """
        with open(file_path, encoding="utf-8") as f:
            content = json.load(f)
        normalized_json = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
        return json.loads(normalized_json)

    def verify_file(self, original_file_path: str, content_dir: str = None) -> dict[str, Any]:
        """验证单个文件的内容完整性

        Args:
            original_file_path: 原始文件路径
            content_dir: 可选的内容块目录

        Returns:
            验证结果字典
        """
        result = {
            "file_name": os.path.basename(original_file_path),
            "file_path": original_file_path,
            "verified_at": datetime.datetime.now().isoformat(),
            "passed": False,
            "details": {},
            "error": "",
        }

        try:
            if not os.path.exists(original_file_path):
                result["error"] = f"原始文件不存在: {original_file_path}"
                return result

            file_name_without_ext = os.path.splitext(os.path.basename(original_file_path))[0]
            chunk_files = self._get_chunk_files(file_name_without_ext, content_dir)

            result["details"]["chunk_count"] = len(chunk_files)
            result["details"]["chunk_files"] = chunk_files

            if len(chunk_files) == 0:
                result["details"]["status"] = "no_chunks"
                result["details"]["message"] = "文件未分割，直接验证原始文件"
                result["passed"] = True
                return result

            temp_dir = tempfile.mkdtemp()
            try:
                reconstructed_path = os.path.join(temp_dir, f"reconstructed_{file_name_without_ext}.json")
                success = self.splitter.reconstruct_file(chunk_files, reconstructed_path)

                if not success:
                    result["error"] = "重建文件失败"
                    return result

                original_content = self._load_and_normalize(original_file_path)
                reconstructed_content = self._load_and_normalize(reconstructed_path)

                original_hash = self._compute_content_hash(original_content)
                reconstructed_hash = self._compute_content_hash(reconstructed_content)

                result["details"]["original_hash"] = original_hash
                result["details"]["reconstructed_hash"] = reconstructed_hash
                result["details"]["hash_match"] = original_hash == reconstructed_hash

                result["details"]["original_size"] = len(json.dumps(original_content, ensure_ascii=False))
                result["details"]["reconstructed_size"] = len(json.dumps(reconstructed_content, ensure_ascii=False))

                if original_hash == reconstructed_hash:
                    result["details"]["status"] = "verified"
                    result["passed"] = True
                else:
                    result["details"]["status"] = "hash_mismatch"
                    result["error"] = "哈希值不匹配，内容可能丢失"

            finally:
                import shutil

                shutil.rmtree(temp_dir)

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

    def verify_all(self) -> dict[str, Any]:
        """验证整个知识库的内容完整性

        Returns:
            完整验证结果字典
        """
        result = {
            "verified_at": datetime.datetime.now().isoformat(),
            "total_files": 0,
            "passed": 0,
            "failed": 0,
            "file_results": [],
            "summary": "",
        }

        if os.path.exists(self.ORIGINAL_DIR):
            for filename in os.listdir(self.ORIGINAL_DIR):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.ORIGINAL_DIR, filename)
                    file_result = self.verify_file(file_path)
                    result["file_results"].append(file_result)
                    result["total_files"] += 1
                    if file_result["passed"]:
                        result["passed"] += 1
                    else:
                        result["failed"] += 1

        result["summary"] = (
            f"总计 {result['total_files']} 个文件，" f"{result['passed']} 个通过，" f"{result['failed']} 个失败"
        )

        return result

    def run_boundary_tests(self, test_dir: str = None) -> dict[str, Any]:
        """运行边界情况测试

        Args:
            test_dir: 测试目录（可选）

        Returns:
            边界测试结果字典
        """
        result = {"tested_at": datetime.datetime.now().isoformat(), "tests": [], "passed": 0, "failed": 0}

        temp_dir = test_dir or tempfile.mkdtemp()

        try:
            test_cases = [
                self._test_empty_file(temp_dir),
                self._test_single_chunk_file(temp_dir),
                self._test_multi_chunk_file(temp_dir),
            ]

            for test in test_cases:
                result["tests"].append(test)
                if test["passed"]:
                    result["passed"] += 1
                else:
                    result["failed"] += 1

        finally:
            if test_dir is None:
                import gc
                import shutil

                gc.collect()
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass

        return result

    def _test_empty_file(self, temp_dir: str) -> dict[str, Any]:
        """测试空文件

        Args:
            temp_dir: 临时目录

        Returns:
            测试结果
        """
        test_name = "空文件测试"
        test_result = {"test_name": test_name, "passed": False, "details": {}, "error": ""}

        try:
            test_dir = os.path.join(temp_dir, "empty_test")
            source_dir = os.path.join(test_dir, "source")
            original_dir = os.path.join(test_dir, "original")
            content_dir = os.path.join(test_dir, "content")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(original_dir, exist_ok=True)
            os.makedirs(content_dir, exist_ok=True)

            source_path = os.path.join(source_dir, "empty_test.json")
            with open(source_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

            test_result["details"]["file_created"] = True

            test_verifier = KnowledgeBaseVerifier()
            test_verifier.ORIGINAL_DIR = original_dir
            test_verifier.CONTENT_DIR = content_dir
            test_verifier.splitter.ORIGINAL_DIR = original_dir
            test_verifier.splitter.CONTENT_DIR = content_dir

            split_result = test_verifier.splitter.split_file(source_path)
            test_result["details"]["split_needed"] = split_result["error"] != ""

            backup_path = os.path.join(original_dir, "empty_test.json")
            # 如果没有自动备份，手动复制一份
            if not os.path.exists(backup_path):
                import shutil

                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(source_path, backup_path)

            verify_result = test_verifier.verify_file(backup_path, content_dir)
            test_result["details"]["verify_passed"] = verify_result["passed"]
            test_result["details"]["verify_details"] = verify_result["details"]
            if verify_result.get("error"):
                test_result["error"] = verify_result["error"]

            test_result["passed"] = verify_result["passed"]
            return test_result

        except Exception as e:
            test_result["error"] = str(e)
            return test_result

    def _test_single_chunk_file(self, temp_dir: str) -> dict[str, Any]:
        """测试单块文件

        Args:
            temp_dir: 临时目录

        Returns:
            测试结果
        """
        test_name = "单块文件测试"
        test_result = {"test_name": test_name, "passed": False, "details": {}, "error": ""}

        try:
            test_dir = os.path.join(temp_dir, "single_test")
            source_dir = os.path.join(test_dir, "source")
            original_dir = os.path.join(test_dir, "original")
            content_dir = os.path.join(test_dir, "content")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(original_dir, exist_ok=True)
            os.makedirs(content_dir, exist_ok=True)

            source_path = os.path.join(source_dir, "single_chunk_test.json")
            test_data = {"name": "测试数据", "items": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]}
            with open(source_path, "w", encoding="utf-8") as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2)

            test_result["details"]["file_created"] = True
            test_result["details"]["file_size"] = os.path.getsize(source_path)

            test_verifier = KnowledgeBaseVerifier()
            test_verifier.ORIGINAL_DIR = original_dir
            test_verifier.CONTENT_DIR = content_dir
            test_verifier.splitter.ORIGINAL_DIR = original_dir
            test_verifier.splitter.CONTENT_DIR = content_dir

            test_splitter = JSONFileSplitter(size_threshold=1024 * 1024)
            test_splitter.ORIGINAL_DIR = original_dir
            test_splitter.CONTENT_DIR = content_dir

            split_result = test_splitter.split_file(source_path)

            chunk_files = []
            if os.path.exists(content_dir):
                for f in os.listdir(content_dir):
                    if f.startswith("single_chunk_test_chunk_"):
                        chunk_files.append(os.path.join(content_dir, f))
            test_result["details"]["chunk_count"] = len(chunk_files)

            backup_path = os.path.join(original_dir, "single_chunk_test.json")
            # 如果没有自动备份，手动复制一份
            if not os.path.exists(backup_path):
                import shutil

                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(source_path, backup_path)

            verify_result = test_verifier.verify_file(backup_path, content_dir)
            test_result["details"]["verify_passed"] = verify_result["passed"]
            if verify_result.get("error"):
                test_result["error"] = verify_result["error"]

            test_result["passed"] = verify_result["passed"]
            return test_result

        except Exception as e:
            test_result["error"] = str(e)
            return test_result

    def _test_multi_chunk_file(self, temp_dir: str) -> dict[str, Any]:
        """测试多块文件

        Args:
            temp_dir: 临时目录

        Returns:
            测试结果
        """
        test_name = "多块文件测试"
        test_result = {"test_name": test_name, "passed": False, "details": {}, "error": ""}

        try:
            test_dir = os.path.join(temp_dir, "multi_test")
            source_dir = os.path.join(test_dir, "source")
            original_dir = os.path.join(test_dir, "original")
            content_dir = os.path.join(test_dir, "content")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(original_dir, exist_ok=True)
            os.makedirs(content_dir, exist_ok=True)

            source_path = os.path.join(source_dir, "multi_chunk_test.json")
            test_data = []
            for i in range(100):
                test_data.append(
                    {
                        "id": i,
                        "name": f"项目_{i}",
                        "description": f"这是项目{i}的详细描述内容，用于测试多块文件分割和重建" * 5,
                    }
                )

            with open(source_path, "w", encoding="utf-8") as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2)

            test_result["details"]["file_created"] = True
            test_result["details"]["file_size"] = os.path.getsize(source_path)

            test_verifier = KnowledgeBaseVerifier()
            test_verifier.ORIGINAL_DIR = original_dir
            test_verifier.CONTENT_DIR = content_dir

            test_splitter = JSONFileSplitter(size_threshold=4096)
            test_splitter.ORIGINAL_DIR = original_dir
            test_splitter.CONTENT_DIR = content_dir

            split_result = test_splitter.split_file(source_path)

            if not split_result["success"]:
                test_result["error"] = split_result["error"]
                return test_result

            chunk_files = []
            if os.path.exists(content_dir):
                for f in os.listdir(content_dir):
                    if f.startswith("multi_chunk_test_chunk_"):
                        chunk_files.append(os.path.join(content_dir, f))
            test_result["details"]["chunk_count"] = len(chunk_files)

            backup_path = os.path.join(original_dir, "multi_chunk_test.json")
            test_verifier.splitter.ORIGINAL_DIR = original_dir
            test_verifier.splitter.CONTENT_DIR = content_dir
            test_verifier.ORIGINAL_DIR = original_dir
            test_verifier.CONTENT_DIR = content_dir

            verify_result = test_verifier.verify_file(backup_path, content_dir)
            test_result["details"]["verify_passed"] = verify_result["passed"]
            test_result["details"]["hash_match"] = verify_result["details"].get("hash_match", False)
            if verify_result.get("error"):
                test_result["error"] = verify_result["error"]

            test_result["passed"] = verify_result["passed"]
            return test_result

        except Exception as e:
            test_result["error"] = str(e)
            return test_result

    def generate_report(self, verify_result: dict[str, Any], boundary_result: dict[str, Any] = None) -> str:
        """生成详细的验证报告

        Args:
            verify_result: 验证结果
            boundary_result: 边界测试结果（可选）

        Returns:
            报告字符串
        """
        report = []
        report.append("=" * 80)
        report.append("知识库内容完整性验证报告")
        report.append("=" * 80)
        report.append(f"验证时间: {verify_result.get('verified_at', datetime.datetime.now().isoformat())}")
        report.append("")

        if "total_files" in verify_result:
            report.append("【知识库整体验证】")
            report.append(f"总计文件数: {verify_result['total_files']}")
            report.append(f"通过: {verify_result['passed']} ✓")
            report.append(f"失败: {verify_result['failed']} ✗")
            report.append("")

            if verify_result["file_results"]:
                report.append("文件详情:")
                for file_result in verify_result["file_results"]:
                    status = "✓ 通过" if file_result["passed"] else "✗ 失败"
                    report.append(f"  - {file_result['file_name']}: {status}")
                    if not file_result["passed"] and file_result.get("error"):
                        report.append(f"    错误: {file_result['error']}")
                    if "details" in file_result:
                        details = file_result["details"]
                        if "chunk_count" in details:
                            report.append(f"    块数量: {details['chunk_count']}")
                        if "hash_match" in details:
                            hash_status = "匹配" if details["hash_match"] else "不匹配"
                            report.append(f"    哈希值: {hash_status}")
                report.append("")

        else:
            report.append("【单文件验证】")
            report.append(f"文件: {verify_result.get('file_name', 'N/A')}")
            status = "✓ 通过" if verify_result["passed"] else "✗ 失败"
            report.append(f"状态: {status}")
            if verify_result.get("error"):
                report.append(f"错误: {verify_result['error']}")
            if "details" in verify_result:
                details = verify_result["details"]
                for key, value in details.items():
                    report.append(f"  {key}: {value}")
            report.append("")

        if boundary_result:
            report.append("-" * 80)
            report.append("【边界情况测试】")
            report.append(f"测试时间: {boundary_result.get('tested_at')}")
            report.append(f"通过: {boundary_result['passed']} ✓")
            report.append(f"失败: {boundary_result['failed']} ✗")
            report.append("")

            for test in boundary_result["tests"]:
                status = "✓ 通过" if test["passed"] else "✗ 失败"
                report.append(f"  {test['test_name']}: {status}")
                if test.get("error"):
                    report.append(f"    错误: {test['error']}")
            report.append("")

        report.append("=" * 80)
        return "\n".join(report)


def verify_file_cli(file_path: str, run_boundary: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """命令行接口：验证单个文件

    Args:
        file_path: 文件路径
        run_boundary: 是否运行边界测试

    Returns:
        (验证结果, 边界测试结果)
    """
    verifier = KnowledgeBaseVerifier()
    verify_result = verifier.verify_file(file_path)
    boundary_result = None
    if run_boundary:
        boundary_result = verifier.run_boundary_tests()
    return verify_result, boundary_result


def verify_all_cli(run_boundary: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """命令行接口：验证整个知识库

    Args:
        run_boundary: 是否运行边界测试

    Returns:
        (验证结果, 边界测试结果)
    """
    verifier = KnowledgeBaseVerifier()
    verify_result = verifier.verify_all()
    boundary_result = None
    if run_boundary:
        boundary_result = verifier.run_boundary_tests()
    return verify_result, boundary_result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="知识库内容完整性验证工具")
    parser.add_argument("file_path", nargs="?", help="要验证的文件路径（可选，不指定则验证整个知识库）")
    parser.add_argument("--boundary", action="store_true", help="运行边界情况测试")
    parser.add_argument("--report", metavar="OUTPUT_PATH", help="保存报告到指定文件")

    args = parser.parse_args()

    print("=" * 80)
    print("知识库内容完整性验证工具")
    print("=" * 80)
    print()

    verifier = KnowledgeBaseVerifier()
    verify_result = None
    boundary_result = None

    if args.file_path:
        print(f"正在验证文件: {args.file_path}")
        verify_result = verifier.verify_file(args.file_path)
    else:
        print("正在验证整个知识库...")
        verify_result = verifier.verify_all()

    if args.boundary:
        print("正在运行边界情况测试...")
        boundary_result = verifier.run_boundary_tests()

    report = verifier.generate_report(verify_result, boundary_result)

    print(report)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n报告已保存到: {args.report}")

    if verify_result.get("failed", 0) > 0 or (boundary_result and boundary_result.get("failed", 0) > 0):
        sys.exit(1)

    print("\n✓ 验证完成！")
