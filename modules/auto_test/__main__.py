"""Command line entry point for the auto_test module."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行 auto_test 模块回归任务。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sort-audit", help="默认回归 13 个字段；利润暂缓，可显式单独核查")
    subparsers.add_parser("delivery-status-regression", add_help=False, help="销售订单交货状态筛选回归，默认仅预览")
    args, remaining = parser.parse_known_args(argv)
    if args.command == "sort-audit":
        from modules.auto_test.core.sales_order_sort_audit import main as run_sort_audit

        return run_sort_audit(remaining)
    if args.command == "delivery-status-regression":
        from modules.auto_test.core.sales_order_delivery_status_regression import main as run_delivery_status_regression

        return run_delivery_status_regression(remaining)
    parser.error(f"不支持的 auto_test 任务: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
