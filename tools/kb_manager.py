#!/usr/bin/env python3
"""知识库管理CLI工具 - 支持批量操作、分割、索引、验证和迁移"""

import argparse
import os
import sys

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

from modules.trae_test.utils.file_splitter import JSONFileSplitter
from modules.trae_test.utils.index_builder_v3 import IndexBuilderV3
from modules.trae_test.utils.kb_monitor import KnowledgeBaseMonitor
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever


class KnowledgeBaseManager:
    """知识库管理器，提供各种管理功能"""

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
            for filename in os.listdir(self.monitor.INDEX_DIR):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.monitor.INDEX_DIR, filename)
                    size = os.path.getsize(file_path)
                    result["index"].append({"filename": filename, "size": size, "size_kb": round(size / 1024, 2)})

        result["summary"] = {
            "original_count": len(result["original"]),
            "content_count": len(result["content"]),
            "index_count": len(result["index"]),
        }

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

    def process_file(self, file_path: str) -> Dict:
        """完整处理文件（分割+索引）

        Args:
            file_path: 文件路径

        Returns:
            处理结果
        """
        return self.monitor.process_file_complete(file_path)

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
            index_path = os.path.join(self.monitor.INDEX_DIR, "files", index_file)
            result["index_exists"] = os.path.exists(index_path)

            if result["index_exists"]:
                chunks = self.retriever.get_all_chunks(file_title)
                result["chunks_exist"] = len(chunks) > 0

                for chunk in chunks:
                    chunk_valid = all(key in chunk for key in ["chunk_index", "total_chunks", "data"])
                    result["chunks_valid"].append({"chunk_index": chunk.get("chunk_index"), "valid": chunk_valid})

                result["success"] = (
                    result["index_exists"]
                    and result["chunks_exist"]
                    and all(item["valid"] for item in result["chunks_valid"])
                )

            return result

        except Exception as e:
            result["error"] = str(e)
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

        result = {"success": False, "source_path": source_path, "target_path": "", "processed": None, "error": ""}

        try:
            if not os.path.exists(source_path):
                result["error"] = f"源文件不存在: {source_path}"
                return result

            if target_title is None:
                target_title = os.path.splitext(os.path.basename(source_path))[0]

            target_filename = f"{target_title}.json"
            target_path = os.path.join(self.monitor.ORIGINAL_DIR, target_filename)

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(source_path, target_path)
            result["target_path"] = target_path

            process_result = self.process_file(target_path)
            result["processed"] = process_result
            result["success"] = process_result["success"]

            return result

        except Exception as e:
            result["error"] = str(e)
            return result

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
    print(f"  原始文件: {result['summary']['original_count']} 个")
    print(f"  内容块: {result['summary']['content_count']} 个")
    print(f"  索引文件: {result['summary']['index_count']} 个")


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
    print(f"块存在: {OK_SIGN if result['chunks_exist'] else FAIL_SIGN}")

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
        print(f"  索引: {OK_SIGN if result['processed']['index']['success'] else FAIL_SIGN}")

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

    # verify 命令
    verify_parser = subparsers.add_parser("verify", help="验证文件完整性")
    verify_parser.add_argument("--title", required=True, help="文件标题（不带扩展名）")

    # migrate 命令
    migrate_parser = subparsers.add_parser("migrate", help="迁移文件到知识库")
    migrate_parser.add_argument("--source", required=True, help="源文件路径")
    migrate_parser.add_argument("--title", help="目标文件标题（可选）")

    # scan 命令
    scan_parser = subparsers.add_parser("scan", help="扫描知识库")

    # process-all 命令
    process_all_parser = subparsers.add_parser("process-all", help="批量处理所有需要处理的文件")

    args = parser.parse_args()

    manager = KnowledgeBaseManager()

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
        result = manager.process_file(args.file)
        if result["split"]:
            print_split_result(result["split"])
        if result["index"]:
            print_index_result(result["index"])
    elif args.command == "verify":
        result = manager.verify_file(args.title)
        print_verify_result(result)
    elif args.command == "migrate":
        result = manager.migrate_file(args.source, args.title)
        print_migrate_result(result)
    elif args.command == "scan":
        result = manager.scan_all()
        print_scan_result(result)
    elif args.command == "process-all":
        result = manager.process_all()
        print_process_all_result(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
