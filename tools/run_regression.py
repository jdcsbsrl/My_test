#!/usr/bin/env python3
"""
运行回归测试并生成可视化报告
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.report_generator import run_regression_tests

if __name__ == "__main__":
    run_regression_tests()
