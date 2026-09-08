#!/usr/bin/env python3
"""
测试报告生成工具
生成可视化的测试报告
"""

import json
import sys
import argparse
from datetime import datetime
from html import escape
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class TestReportGenerator:
    def __init__(self):
        self.results = []
        self.start_time = datetime.now()
        self.end_time = None
        self.planned_count = 0

    @property
    def exit_code(self) -> int:
        if any(r["status"] == "FAIL" for r in self.results):
            return 1
        if not self.results or len(self.results) < self.planned_count:
            return 2
        return 2 if any(r["status"] != "PASS" for r in self.results) else 0

    def summary(self) -> dict:
        decision = getattr(self, "release_decision", None)
        conclusion = (
            {"READY_FOR_DELIVERY": "可交付", "BLOCKED": "阻断", "REQUIRES_REVIEW": "需要复核", "INCOMPLETE": "验证不完整"}.get(
                decision.get("status"), "未判定"
            )
            if isinstance(decision, dict)
            else {0: "通过", 1: "失败", 2: "验证不完整"}[self.exit_code]
        )
        return {
            "total": len(self.results),
            "planned": max(self.planned_count, len(self.results)),
            "executed": sum(r["status"] in {"PASS", "FAIL"} for r in self.results),
            "passed": sum(r["status"] == "PASS" for r in self.results),
            "failed": sum(r["status"] == "FAIL" for r in self.results),
            "skipped": sum(r["status"] == "SKIP" for r in self.results),
            "blocked": sum(r["status"] == "BLOCKED" for r in self.results),
            "conclusion": conclusion,
            "release_decision": decision,
        }

    def add_test_result(self, test_name: str, status: str, message: str = "", duration: float = 0):
        if status not in {"PASS", "FAIL", "SKIP", "BLOCKED"}:
            raise ValueError("Unknown test status")
        self.results.append(
            {
                "test_name": test_name,
                "status": status,
                "message": message,
                "duration": duration,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def generate_html_report(self, output_path: str = None) -> str:
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")

        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>test_erp 回归测试报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            background: #f5f5f5;
            }}
        .container {{ max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            overflow: hidden;
            }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; }}
        .summary {{ display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
            }}
        .summary-card {{ text-align: center;
            padding: 20px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }}
        .summary-card .number {{ font-size: 36px; font-weight: bold; }}
        .summary-card.pass {{ color: #10b981; }}
        .summary-card.fail {{ color: #ef4444; }}
        .summary-card.skip {{ color: #f59e0b; }}
        .summary-card.total {{ color: #6366f1; }}
        .summary-card .label {{ font-size: 14px; opacity: 0.7; margin-top: 5px; }}
        .results {{ padding: 30px; }}
        .results h2 {{ font-size: 20px; margin-bottom: 20px; color: #374151; }}
        .test-row {{ display: flex;
            align-items: center;
            padding: 15px;
            border-bottom: 1px solid #e5e7eb;
            transition: background 0.2s;
            }}
        .test-row:hover {{ background: #f9fafb; }}
        .test-row:last-child {{ border-bottom: none; }}
        .status-badge {{ width: 10px; height: 10px; border-radius: 50%; margin-right: 15px; }}
        .status-badge.pass {{ background: #10b981; }}
        .status-badge.fail {{ background: #ef4444; }}
        .status-badge.skip {{ background: #f59e0b; }}
        .test-name {{ flex: 1; font-weight: 500; color: #374151; }}
        .test-message {{ flex: 1; color: #6b7280; font-size: 14px; }}
        .test-duration {{ color: #9ca3af; font-size: 14px; }}
        .footer {{ padding: 20px; text-align: center; color: #9ca3af; font-size: 14px; background: #f8f9fa; }}
        .chart-container {{ padding: 30px; background: white; }}
        .chart-bar {{ display: flex; align-items: flex-end; height: 100px; gap: 20px; }}
        .chart-item {{ flex: 1; display: flex; flex-direction: column; align-items: center; }}
        .chart-bar-inner {{ width: 100%; border-radius: 4px 4px 0 0; transition: height 0.5s; }}
        .chart-label {{ margin-top: 8px; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>test_erp 回归测试报告</h1>
            <p>结论: {self.summary()['conclusion']}
                | 计划: {self.summary()['planned']}
                | 实际执行: {self.summary()['executed']}
                | 环境/数据阻断: {self.summary()['blocked']}</p>
            <p>生成时间: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')} | 执行时长: {duration:.2f} 秒</p>
        </div>

        <div class="summary">
            <div class="summary-card total">
                <div class="number">{len(self.results)}</div>
                <div class="label">总测试数</div>
            </div>
            <div class="summary-card pass">
                <div class="number">{passed}</div>
                <div class="label">通过</div>
            </div>
            <div class="summary-card fail">
                <div class="number">{failed}</div>
                <div class="label">失败</div>
            </div>
            <div class="summary-card skip">
                <div class="number">{skipped}</div>
                <div class="label">跳过</div>
            </div>
        </div>

        <div class="chart-container">
            <h2 style="margin-bottom: 20px;">测试结果分布</h2>
            <div class="chart-bar">
                <div class="chart-item">
                    <div class="chart-bar-inner"
                         style="height: {passed/len(self.results)*100 if self.results else 0}%;
            background: #10b981;"></div>
                    <div class="chart-label">通过 ({passed})</div>
                </div>
                <div class="chart-item">
                    <div class="chart-bar-inner"
                         style="height: {failed/len(self.results)*100 if self.results else 0}%;
            background: #ef4444;"></div>
                    <div class="chart-label">失败 ({failed})</div>
                </div>
                <div class="chart-item">
                    <div class="chart-bar-inner"
                         style="height: {skipped/len(self.results)*100 if self.results else 0}%;
            background: #f59e0b;"></div>
                    <div class="chart-label">跳过 ({skipped})</div>
                </div>
            </div>
        </div>

        <div class="results">
            <h2>测试用例详情</h2>
            {''.join([f'''
            <div class="test-row">
                <div class="status-badge {r['status'].lower()}"></div>
                <div class="test-name">{escape(str(r['test_name']))}</div>
                <div class="test-message">{escape(str(r['message']))}</div>
                <div class="test-duration">{r['duration']:.2f}s</div>
            </div>
            ''' for r in self.results])}
        </div>

        <div class="footer">
            <p>报告由 test_erp 测试框架自动生成</p>
        </div>
    </div>
</body>
</html>
        """

        if output_path:
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        return html_content

    def generate_json_report(self, output_path: str = None) -> str:
        report = {
            "generated_at": datetime.now().isoformat(),
            "duration": (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            "summary": self.summary(),
            "results": self.results,
        }

        json_str = json.dumps(report, ensure_ascii=False, indent=2)

        if output_path:
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)

        return json_str


def run_regression_tests(*, env_name: str = "test", scope: str = "module"):
    """Execute approved read-only queries and render their business results."""
    from modules.auto_test.core.regression_checks import execute_sales_queries, planned_scenario_count
    from modules.auto_test.core.regression_session import regression_session
    from modules.auto_test.facades.api.sales_order_facade import SalesOrderFacade
    from modules.trae_test.orchestrator.release_quality_gate import ReleaseQualityGate
    from modules.trae_test.utils.runtime_paths import runtime_dir

    if env_name not in {"test", "uat"} or scope not in {"smoke", "module", "release"}:
        raise ValueError("Only test/uat and smoke/module/release are supported")
    report = TestReportGenerator()
    report.planned_count = planned_scenario_count(scope)
    try:
        with regression_session(env_name) as client:
            execute_sales_queries(SalesOrderFacade(client), report, scope=scope)
    except Exception as exc:
        report.add_test_result("初始化", "BLOCKED", type(exc).__name__)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    root = runtime_dir("reports")
    decision = ReleaseQualityGate().evaluate(
        cases=[],
        regression_report=report,
        release_scope=scope,
        require_regression=True,
        require_p0=False,
        require_cases=False,
    )
    report.release_decision = decision.to_dict()
    report.generate_html_report(str(root / f"regression_report_{stamp}.html"))
    report.generate_json_report(str(root / f"regression_report_{stamp}.json"))
    print(report.summary())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 test_erp 回归测试 HTML/JSON 报告")
    parser.add_argument("--run-regression", action="store_true", help="执行回归测试并生成报告")
    args = parser.parse_args()
    if not args.run_regression:
        parser.print_help()
        return 0
    report = run_regression_tests()
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
