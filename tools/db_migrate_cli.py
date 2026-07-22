from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

OK = "[OK]"
FAIL = "[FAIL]"


def cmd_init_db(_args: argparse.Namespace) -> None:
    from modules.trae_test.core.migration.init_db import create_all_tables

    print("正在初始化数据库表结构...")
    try:
        create_all_tables()
        print(f"{OK} 数据库表创建成功")
    except Exception as e:
        print(f"{FAIL} 创建失败: {e}")
        sys.exit(1)


def cmd_migrate(args: argparse.Namespace) -> None:
    from modules.trae_test.core.migration.init_db import create_all_tables
    from modules.trae_test.core.migration.migrator import migrate_all, migrate_file

    create_all_tables()

    if args.file:
        print(f"迁移文件: {args.file}")
        result = migrate_file(args.file)
        if result["success"]:
            print(f"{OK} {result['file']}: {result['phases']}")
        else:
            print(f"{FAIL} {result['file']}: {result['error']}")
            sys.exit(1)
        return

    if args.all:
        print("开始全量迁移...")
        result = migrate_all()
        print(f"\n总计: {result['total']} 个文件")
        print(f"  迁移: {result['migrated']}")
        print(f"  跳过: {result['skipped']}")
        print(f"  失败: {result['failed']}")
        for d in result["details"]:
            marker = OK if d["success"] else FAIL
            print(f"  {marker} {d['file']}", end="")
            if not d["success"] and d.get("error"):
                print(f" -> {d['error']}")
            else:
                print()
        if not result["success"]:
            sys.exit(1)
        return

    print("请指定 --all 或 --file <文件名>")


def cmd_verify(_args: argparse.Namespace) -> None:
    from modules.trae_test.core.migration.migrator import verify_all

    print("正在验证数据完整性...")
    result = verify_all()

    print(f"\n文件哈希比对: {result['total']} 个文件")
    print(f"  匹配: {result['matched']}")
    print(f"  不匹配: {result['mismatched']}")

    for d in result["details"]:
        marker = OK if d["in_db"] else FAIL
        print(f"  {marker} {d['file']}")

    records = result.get("db_records", {})
    if records:
        print("\n数据库记录统计:")
        print(f"  kb_files: {records.get('kb_files', 0)}")
        print(f"  kb_requirements: {records.get('kb_requirements', 0)}")
        print(f"  kb_business_rules: {records.get('kb_business_rules', 0)}")
        print(f"  kb_problems: {records.get('kb_problems', 0)}")
        print(f"  kb_test_cases: {records.get('kb_test_cases', 0)}")

    if not result["success"]:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库数据库迁移工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("init-db", help="仅创建数据库表结构")

    migrate_parser = subparsers.add_parser("migrate", help="执行数据迁移")
    migrate_parser.add_argument("--all", action="store_true", help="迁移所有文件")
    migrate_parser.add_argument("--file", type=str, help="迁移指定文件")

    subparsers.add_parser("verify", help="验证迁移数据完整性")

    args = parser.parse_args()

    commands = {
        "init-db": cmd_init_db,
        "migrate": cmd_migrate,
        "verify": cmd_verify,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
