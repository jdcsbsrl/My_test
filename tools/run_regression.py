#!/usr/bin/env python3
"""
运行回归测试并生成可视化报告
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.report_generator import run_regression_tests


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 TEST 环境回归测试并生成报告")
    parser.parse_args()
    report = run_regression_tests()
    failed = sum(1 for item in report.results if item["status"] == "FAIL")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
