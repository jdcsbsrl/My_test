#!/usr/bin/env python3
"""
知识库数据库与缓存交互工具
提供 PostgreSQL 表查询和 Redis 缓存操作功能
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# DATABASE_URL must be provided by the environment or a local .env file.
# Never embed database credentials in this administrative CLI.

GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def print_menu():
    print(f"\n{BLUE}=" * 60 + RESET)
    print(f"{BLUE}        PostgreSQL 和 Redis 交互工具{RESET}")
    print(f"{BLUE}=" * 60 + RESET)
    print("\n请选择操作:")
    print("  1. 查看 PostgreSQL 所有表")
    print("  2. 查询指定表数据")
    print("  3. 搜索知识库内容")
    print("  4. 查看 Redis 缓存键")
    print("  5. 获取 Redis 缓存内容")
    print("  6. 清空 Redis 缓存")
    print("  7. 统计信息")
    print("  0. 退出")
    return input("\n输入选项 (0-7): ")


def show_tables():
    from modules.trae_test.core.db_pool import get_session
    from modules.trae_test.core.migration.schema import (
        KBBusinessRule,
        KBChunk,
        KBFile,
        KBProblem,
        KBRequirement,
        KBTestCase,
    )

    session = get_session()
    try:
        print(f"\n{YELLOW}PostgreSQL 数据表列表:{RESET}")
        tables = [
            ("kb_files", "知识库文件元数据", KBFile),
            ("kb_chunks", "文件分块内容", KBChunk),
            ("kb_requirements", "需求清单", KBRequirement),
            ("kb_business_rules", "业务规则", KBBusinessRule),
            ("kb_problems", "线上问题", KBProblem),
            ("kb_test_cases", "测试用例", KBTestCase),
        ]

        print(f"{'表名':<20} {'说明':<20} {'记录数'}")
        print("-" * 50)
        for name, desc, model in tables:
            count = session.query(model).count()
            print(f"{name:<20} {desc:<20} {count}")

    finally:
        session.close()


def query_table():
    table_name = input(
        "请输入表名 (kb_files/kb_chunks/kb_requirements/kb_business_rules/kb_problems/kb_test_cases): "
    ).strip()

    from modules.trae_test.core.db_pool import get_session
    from modules.trae_test.core.migration.schema import (
        KBBusinessRule,
        KBChunk,
        KBFile,
        KBProblem,
        KBRequirement,
        KBTestCase,
    )

    table_map = {
        "kb_files": KBFile,
        "kb_chunks": KBChunk,
        "kb_requirements": KBRequirement,
        "kb_business_rules": KBBusinessRule,
        "kb_problems": KBProblem,
        "kb_test_cases": KBTestCase,
    }

    if table_name not in table_map:
        print(f"{RED}错误: 表名不存在{RESET}")
        return

    model = table_map[table_name]
    session = get_session()

    try:
        limit = int(input("输入显示条数 (默认 10): ") or "10")
        records = session.query(model).limit(limit).all()

        print(f"\n{YELLOW}表 {table_name} 的前 {len(records)} 条记录:{RESET}")
        for i, record in enumerate(records, 1):
            print(f"\n{GREEN}--- 记录 {i} ---{RESET}")
            for attr in dir(record):
                if not attr.startswith("_") and attr not in ["metadata", "__mapper__"]:
                    value = getattr(record, attr)
                    if isinstance(value, dict):
                        value = json.dumps(value, ensure_ascii=False, indent=2)
                    elif isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"  {attr}: {value}")

    finally:
        session.close()


def search_knowledge():
    keyword = input("请输入搜索关键词: ").strip()

    from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

    r = KnowledgeRetriever()

    print(f"\n{YELLOW}正在搜索关键词: {keyword}{RESET}")
    result = r.retrieve(keyword)

    if result:
        print(f"\n{GREEN}搜索结果 ({type(result).__name__}):{RESET}")
        if isinstance(result, dict):
            for key, value in result.items():
                print(f"\n  {key}:")
                if isinstance(value, dict):
                    for k, v in list(value.items())[:3]:
                        if isinstance(v, str) and len(v) > 50:
                            v = v[:50] + "..."
                        print(f"    {k}: {v}")
        elif isinstance(result, list):
            for i, item in enumerate(result[:5], 1):
                print(f"\n  {i}. {json.dumps(item, ensure_ascii=False)[:150]}...")
    else:
        print(f"{RED}未找到相关结果{RESET}")


def show_redis_keys():
    from modules.trae_test.core import cache_manager

    client = cache_manager._try_client()
    if client is None:
        print(f"{RED}Redis 不可用{RESET}")
        return

    print(f"\n{YELLOW}Redis 缓存键列表:{RESET}")
    keys = list(client.scan_iter(match="*", count=100))

    if keys:
        print(f"{'键名':<40} {'TTL(秒)'}")
        print("-" * 50)
        for key in sorted(keys):
            ttl = client.ttl(key)
            print(f"{key:<40} {ttl}")
    else:
        print("  暂无缓存键")


def get_redis_value():
    from modules.trae_test.core import cache_manager

    client = cache_manager._try_client()
    if client is None:
        print(f"{RED}Redis 不可用{RESET}")
        return

    key = input("请输入缓存键名: ").strip()
    value = client.get(key)

    if value is not None:
        try:
            value = json.loads(value)
            print(f"\n{GREEN}缓存内容:{RESET}")
            print(json.dumps(value, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print(f"\n{GREEN}缓存内容:{RESET}")
            print(value)
    else:
        print(f"{RED}键不存在{RESET}")


def clear_redis_cache():
    from modules.trae_test.core import cache_manager

    confirm = input("确定要清空所有 Redis 缓存吗? (y/N): ").strip().lower()
    if confirm != "y":
        print("操作取消")
        return

    success = cache_manager.flush_cache()
    if success:
        print(f"{GREEN}缓存清空成功{RESET}")
    else:
        print(f"{RED}缓存清空失败{RESET}")


def show_stats():
    print(f"\n{YELLOW}数据库统计信息:{RESET}")
    show_tables()

    print(f"\n{YELLOW}\nRedis 统计信息:{RESET}")
    from modules.trae_test.core import cache_manager

    client = cache_manager._try_client()

    if client is not None:
        info = client.info()
        print(f"  Redis 版本: {info.get('redis_version', '未知')}")
        print(f"  已用内存: {info.get('used_memory_human', '未知')}")
        print(f"  连接数: {info.get('connected_clients', 0)}")
        print(f"  键数量: {client.dbsize()}")
    else:
        print("  Redis 不可用")


def main():
    while True:
        choice = print_menu()

        if choice == "1":
            show_tables()
        elif choice == "2":
            query_table()
        elif choice == "3":
            search_knowledge()
        elif choice == "4":
            show_redis_keys()
        elif choice == "5":
            get_redis_value()
        elif choice == "6":
            clear_redis_cache()
        elif choice == "7":
            show_stats()
        elif choice == "0":
            print("退出工具")
            break
        else:
            print(f"{RED}无效选项，请输入 0-7{RESET}")


if __name__ == "__main__":
    main()
