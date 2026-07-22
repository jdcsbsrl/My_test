#!/usr/bin/env python3
"""
测试报告生成工具
生成可视化的测试报告
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestReportGenerator:
    def __init__(self):
        self.results = []
        self.start_time = datetime.now()
        self.end_time = None

    def add_test_result(self, test_name: str, status: str, message: str = "", duration: float = 0):
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
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; padding: 30px; background: #f8f9fa; }}
        .summary-card {{ text-align: center; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        .summary-card .number {{ font-size: 36px; font-weight: bold; }}
        .summary-card.pass {{ color: #10b981; }}
        .summary-card.fail {{ color: #ef4444; }}
        .summary-card.skip {{ color: #f59e0b; }}
        .summary-card.total {{ color: #6366f1; }}
        .summary-card .label {{ font-size: 14px; opacity: 0.7; margin-top: 5px; }}
        .results {{ padding: 30px; }}
        .results h2 {{ font-size: 20px; margin-bottom: 20px; color: #374151; }}
        .test-row {{ display: flex; align-items: center; padding: 15px; border-bottom: 1px solid #e5e7eb; transition: background 0.2s; }}
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
                    <div class="chart-bar-inner" style="height: {passed/len(self.results)*100 if self.results else 0}%; background: #10b981;"></div>
                    <div class="chart-label">通过 ({passed})</div>
                </div>
                <div class="chart-item">
                    <div class="chart-bar-inner" style="height: {failed/len(self.results)*100 if self.results else 0}%; background: #ef4444;"></div>
                    <div class="chart-label">失败 ({failed})</div>
                </div>
                <div class="chart-item">
                    <div class="chart-bar-inner" style="height: {skipped/len(self.results)*100 if self.results else 0}%; background: #f59e0b;"></div>
                    <div class="chart-label">跳过 ({skipped})</div>
                </div>
            </div>
        </div>

        <div class="results">
            <h2>测试用例详情</h2>
            {''.join([f'''
            <div class="test-row">
                <div class="status-badge {r['status'].lower()}"></div>
                <div class="test-name">{r['test_name']}</div>
                <div class="test-message">{r['message']}</div>
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
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r["status"] == "PASS"),
                "failed": sum(1 for r in self.results if r["status"] == "FAIL"),
                "skipped": sum(1 for r in self.results if r["status"] == "SKIP"),
            },
            "results": self.results,
        }

        json_str = json.dumps(report, ensure_ascii=False, indent=2)

        if output_path:
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_str)

        return json_str


def run_regression_tests():
    """运行回归测试并生成报告"""
    report = TestReportGenerator()

    print("=" * 60)
    print("test_erp 查询功能回归测试")
    print("=" * 60)
    print()

    from modules.auto_test.api import APIClient
    from modules.auto_test.core import get_environment
    from modules.auto_test.facades import SalesOrderFacade

    try:
        env = get_environment("test")
        print(f"✓ 环境配置加载成功: {env.name}")
        print(f"  - API基础URL: {env.endpoints.api_base_url}")

        client = APIClient(env.endpoints.api_base_url)
        facade = SalesOrderFacade(client)

        tests = [
            ("基础查询-无筛选条件", lambda: facade.query_orders(page_num=1, page_size=10)),
            ("销售单号搜索-精确匹配", lambda: facade.query_orders(orderNo="SKU2024042400004", pageNum=1, pageSize=10)),
            ("销售单号搜索-包含匹配", lambda: facade.query_orders(orderNo="20240424", pageNum=1, pageSize=10)),
            ("订单状态筛选", lambda: facade.query_orders(orderStatus="0", pageNum=1, pageSize=10)),
            ("分页参数验证(1/10)", lambda: facade.query_orders(page_num=1, page_size=10)),
            ("分页参数验证(2/10)", lambda: facade.query_orders(page_num=2, page_size=10)),
            ("搜索条件组合测试", lambda: facade.query_orders(orderNo="2024", sku="DMS", pageNum=1, pageSize=10)),
            ("空值筛选验证", lambda: facade.query_orders(orderNo="", pageNum=1, pageSize=10)),
        ]

        for test_name, test_func in tests:
            try:
                response = test_func()
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") in (200, 0):
                        print(f"✓ {test_name}")
                        report.add_test_result(test_name, "PASS", "测试通过")
                    else:
                        print(f"✗ {test_name} - 业务码错误: {data.get('msg')}")
                        report.add_test_result(test_name, "FAIL", f"业务码错误: {data.get('msg')}")
                else:
                    print(f"✗ {test_name} - HTTP状态码: {response.status_code}")
                    report.add_test_result(test_name, "FAIL", f"HTTP状态码: {response.status_code}")
            except Exception as e:
                print(f"✗ {test_name} - 异常: {str(e)[:50]}")
                report.add_test_result(test_name, "FAIL", f"异常: {str(e)[:50]}")

        client.close()

    except Exception as e:
        print(f"✗ 测试初始化失败: {e}")
        report.add_test_result("初始化", "FAIL", f"初始化失败: {e}")

    print()
    print("=" * 60)
    print("生成测试报告")
    print("=" * 60)

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = str(reports_dir / f"regression_report_{timestamp}.html")
    json_path = str(reports_dir / f"regression_report_{timestamp}.json")

    report.generate_html_report(html_path)
    report.generate_json_report(json_path)

    print(f"✓ HTML报告: {html_path}")
    print(f"✓ JSON报告: {json_path}")
    print()

    summary = report.generate_json_report()
    summary_data = json.loads(summary)
    print("测试汇总:")
    print(f"  总测试数: {summary_data['summary']['total']}")
    print(f"  通过: {summary_data['summary']['passed']}")
    print(f"  失败: {summary_data['summary']['failed']}")
    print(f"  跳过: {summary_data['summary']['skipped']}")

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

    return report


if __name__ == "__main__":
    run_regression_tests()
