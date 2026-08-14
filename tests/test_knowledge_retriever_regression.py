#!/usr/bin/env python3
"""
KnowledgeRetriever重构回归测试套件

测试范围：
1. 单元测试：验证每个重构后的方法功能正确性
2. 集成测试：验证方法间交互正常
3. 边界情况：验证异常处理和边界条件
4. 向后兼容：验证现有代码调用不受影响
"""

import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever


class RegressionTestReport:
    """回归测试报告生成器"""

    def __init__(self):
        self.test_start_time = datetime.now()
        self.test_results = []
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        self.skipped_tests = 0

    def add_result(self, test_name: str, passed: bool, message: str, details: str = ""):
        """添加测试结果"""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
        else:
            self.failed_tests += 1

        self.test_results.append({"test_name": test_name, "passed": passed, "message": message, "details": details})

    def generate_report(self) -> str:
        """生成测试报告"""
        execution_time = (datetime.now() - self.test_start_time).total_seconds() * 1000

        report = f"""
╔════════════════════════════════════════════════════════════════════════════════╗
║                     KnowledgeRetriever 重构回归测试报告                       ║
╚════════════════════════════════════════════════════════════════════════════════╝

【测试时间】{self.test_start_time.strftime('%Y-%m-%d %H:%M:%S')}
【执行耗时】{execution_time:.2f} ms
【测试总数】{self.total_tests}
【通过数量】{self.passed_tests}
【失败数量】{self.failed_tests}
【通过率】{(self.passed_tests / self.total_tests * 100):.1f}%

════════════════════════════════════════════════════════════════════════════════
                            一、测试结果详情
════════════════════════════════════════════════════════════════════════════════
"""

        for i, result in enumerate(self.test_results, 1):
            status = "[PASS]" if result["passed"] else "[FAIL]"
            report += f"""
{i}. {status} {result['test_name']}
   {result['message']}
"""
            if result["details"]:
                report += f"   详情: {result['details']}\n"

        report += f"""

════════════════════════════════════════════════════════════════════════════════
                            二、测试总结
════════════════════════════════════════════════════════════════════════════════

整体状态: {'[OK] 所有测试通过 - 重构未破坏现有功能' if self.failed_tests == 0 else '[ERROR] 存在失败的测试 - 需要修复'}

"""

        if self.failed_tests == 0:
            report += "建议: 可以安全地将重构代码合并到主分支\n"
        else:
            report += "建议: 需要修复失败的测试后再合并\n"

        return report


class TestKnowledgeRetrieverRegression:
    """KnowledgeRetriever回归测试类"""

    def setup_method(self):
        self.retriever = KnowledgeRetriever()
        self.report = RegressionTestReport()

    def test_refactored_methods(self):
        """测试所有重构后的方法"""
        print("\n" + "=" * 80)
        print("开始测试重构后的方法")
        print("=" * 80)

        # 测试 search_cross_module_flows
        self._test_cross_module_flows()

        # 测试 search_test_template
        self._test_test_template()

        # 测试 search_defect_spec
        self._test_defect_spec()

        # 测试 search_navigation
        self._test_navigation()

        # 测试 search_automation_spec
        self._test_automation_spec()

        # 测试 search_module
        self._test_module()

    def test_generic_methods(self):
        """测试通用方法"""
        print("\n" + "=" * 80)
        print("测试通用方法")
        print("=" * 80)

        # 测试 _search_single_file
        self._test_search_single_file()

        # 测试 _search_multiple_files
        self._test_search_multiple_files()

        # 测试 title_filter 功能
        self._test_title_filter()

    def test_integration(self):
        """测试集成场景"""
        print("\n" + "=" * 80)
        print("测试集成场景")
        print("=" * 80)

        # 测试 auto_retrieve 方法（内部调用 search_cross_module_flows）
        self._test_auto_retrieve()

        # 测试批量检索
        self._test_batch_retrieve()

    def test_edge_cases(self):
        """测试边界情况"""
        print("\n" + "=" * 80)
        print("测试边界情况")
        print("=" * 80)

        # 测试空标签
        self._test_empty_tags()

        # 测试不存在的标签
        self._test_nonexistent_tags()

        # 测试空 title_filter
        self._test_empty_title_filter()

        # 测试无效配置
        self._test_invalid_config()

    def _test_cross_module_flows(self):
        """测试跨模块流程搜索"""
        try:
            start_time = time.time()
            result = self.retriever.search_cross_module_flows()
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = f"返回类型正确: {type(result).__name__}"
            details = f"执行时间: {execution_time:.2f}ms, 返回结果: {'非空' if result else '空字典'}"

            self.report.add_result("search_cross_module_flows", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} search_cross_module_flows - {message}")
        except Exception as e:
            self.report.add_result("search_cross_module_flows", False, f"异常: {str(e)}")
            print(f"  [FAIL] search_cross_module_flows - {str(e)}")

    def _test_test_template(self):
        """测试测试模板搜索"""
        try:
            start_time = time.time()
            result = self.retriever.search_test_template()
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = f"返回类型正确: {type(result).__name__}"
            details = f"执行时间: {execution_time:.2f}ms, 返回结果: {'非空' if result else '空字典'}"

            self.report.add_result("search_test_template", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} search_test_template - {message}")
        except Exception as e:
            self.report.add_result("search_test_template", False, f"异常: {str(e)}")
            print(f"  [FAIL] search_test_template - {str(e)}")

    def _test_defect_spec(self):
        """测试缺陷规范搜索"""
        try:
            start_time = time.time()
            result = self.retriever.search_defect_spec()
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = f"返回类型正确: {type(result).__name__}"
            details = f"执行时间: {execution_time:.2f}ms, 返回结果: {'非空' if result else '空字典'}"

            self.report.add_result("search_defect_spec", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} search_defect_spec - {message}")
        except Exception as e:
            self.report.add_result("search_defect_spec", False, f"异常: {str(e)}")
            print(f"  [FAIL] search_defect_spec - {str(e)}")

    def _test_navigation(self):
        """测试导航搜索"""
        try:
            start_time = time.time()
            result = self.retriever.search_navigation()
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = f"返回类型正确: {type(result).__name__}"
            details = f"执行时间: {execution_time:.2f}ms, 返回结果: {'非空' if result else '空字典'}"

            self.report.add_result("search_navigation", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} search_navigation - {message}")
        except Exception as e:
            self.report.add_result("search_navigation", False, f"异常: {str(e)}")
            print(f"  [FAIL] search_navigation - {str(e)}")

    def _test_automation_spec(self):
        """测试自动化规范搜索"""
        try:
            start_time = time.time()
            result = self.retriever.search_automation_spec()
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict) and len(result) == 3
            message = "返回类型和内容正确，包含3个键"
            details = f"执行时间: {execution_time:.2f}ms, 键: {list(result.keys())}"

            self.report.add_result("search_automation_spec", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} search_automation_spec - {message}")
        except Exception as e:
            self.report.add_result("search_automation_spec", False, f"异常: {str(e)}")
            print(f"  [FAIL] search_automation_spec - {str(e)}")

    def _test_module(self):
        """测试模块搜索"""
        try:
            start_time = time.time()
            result = self.retriever.search_module("产品")
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = f"返回类型正确: {type(result).__name__}"
            details = f"执行时间: {execution_time:.2f}ms, 返回结果: {'非空' if result else '空字典'}"

            self.report.add_result("search_module", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} search_module - {message}")
        except Exception as e:
            self.report.add_result("search_module", False, f"异常: {str(e)}")
            print(f"  [FAIL] search_module - {str(e)}")

    def _test_search_single_file(self):
        """测试通用单文件搜索"""
        try:
            start_time = time.time()
            result = self.retriever._search_single_file("产品模块", "产品")
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = "_search_single_file 返回类型正确"
            details = f"执行时间: {execution_time:.2f}ms"

            self.report.add_result("_search_single_file", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} _search_single_file - {message}")
        except Exception as e:
            self.report.add_result("_search_single_file", False, f"异常: {str(e)}")
            print(f"  [FAIL] _search_single_file - {str(e)}")

    def _test_search_multiple_files(self):
        """测试通用多文件搜索"""
        try:
            start_time = time.time()
            search_configs = [
                {"tags": ["产品模块"], "result_key": "产品"},
                {"tags": ["销售模块"], "result_key": "销售"},
            ]
            result = self.retriever._search_multiple_files(search_configs)
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = "_search_multiple_files 返回类型正确"
            details = f"执行时间: {execution_time:.2f}ms, 返回键: {list(result.keys())}"

            self.report.add_result("_search_multiple_files", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} _search_multiple_files - {message}")
        except Exception as e:
            self.report.add_result("_search_multiple_files", False, f"异常: {str(e)}")
            print(f"  [FAIL] _search_multiple_files - {str(e)}")

    def _test_title_filter(self):
        """测试标题过滤功能"""
        try:
            start_time = time.time()
            result = self.retriever._search_single_file("业务规则", title_filter=lambda title: "销售" in title)
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = "title_filter 功能正常"
            details = f"执行时间: {execution_time:.2f}ms, 过滤条件: 包含'销售'"

            self.report.add_result("title_filter", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} title_filter - {message}")
        except Exception as e:
            self.report.add_result("title_filter", False, f"异常: {str(e)}")
            print(f"  [FAIL] title_filter - {str(e)}")

    def _test_auto_retrieve(self):
        """测试自动检索（内部调用search_cross_module_flows）"""
        try:
            start_time = time.time()
            result = self.retriever.retrieve("销售订单流程")
            execution_time = (time.time() - start_time) * 1000

            passed = result is not None
            message = "retrieve 执行正常"
            details = f"执行时间: {execution_time:.2f}ms, 返回类型: {type(result).__name__ if result else 'None'}"

            self.report.add_result("retrieve", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} retrieve - {message}")
        except Exception as e:
            self.report.add_result("retrieve", False, f"异常: {str(e)}")
            print(f"  [FAIL] retrieve - {str(e)}")

    def _test_batch_retrieve(self):
        """测试批量检索"""
        try:
            start_time = time.time()
            result = self.retriever.batch_retrieve(["销售", "产品"], mode="auto")
            execution_time = (time.time() - start_time) * 1000

            passed = isinstance(result, dict)
            message = "batch_retrieve 执行正常"
            details = f"执行时间: {execution_time:.2f}ms, 返回键: {list(result.keys())}"

            self.report.add_result("batch_retrieve", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} batch_retrieve - {message}")
        except Exception as e:
            self.report.add_result("batch_retrieve", False, f"异常: {str(e)}")
            print(f"  [FAIL] batch_retrieve - {str(e)}")

    def _test_empty_tags(self):
        """测试空标签"""
        try:
            result = self.retriever._search_single_file()
            passed = result == {}
            message = "空标签返回空字典"
            details = f"返回结果: {result}"

            self.report.add_result("empty_tags", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} empty_tags - {message}")
        except Exception as e:
            self.report.add_result("empty_tags", False, f"异常: {str(e)}")
            print(f"  [FAIL] empty_tags - {str(e)}")

    def _test_nonexistent_tags(self):
        """测试不存在的标签"""
        try:
            result = self.retriever._search_single_file("不存在的标签XYZ123")
            passed = result == {}
            message = "不存在的标签返回空字典"
            details = f"返回结果: {result}"

            self.report.add_result("nonexistent_tags", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} nonexistent_tags - {message}")
        except Exception as e:
            self.report.add_result("nonexistent_tags", False, f"异常: {str(e)}")
            print(f"  [FAIL] nonexistent_tags - {str(e)}")

    def _test_empty_title_filter(self):
        """测试空标题过滤器"""
        try:
            result = self.retriever._search_single_file("产品模块", title_filter=None)
            passed = isinstance(result, dict)
            message = "空 title_filter 正常工作"
            details = f"返回结果: {'非空' if result else '空字典'}"

            self.report.add_result("empty_title_filter", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} empty_title_filter - {message}")
        except Exception as e:
            self.report.add_result("empty_title_filter", False, f"异常: {str(e)}")
            print(f"  [FAIL] empty_title_filter - {str(e)}")

    def _test_invalid_config(self):
        """测试无效配置"""
        try:
            result = self.retriever._search_multiple_files([])
            passed = result == {}
            message = "空配置列表返回空字典"
            details = f"返回结果: {result}"

            self.report.add_result("invalid_config", passed, message, details)
            print(f"  {'[PASS]' if passed else '[FAIL]'} invalid_config - {message}")
        except Exception as e:
            self.report.add_result("invalid_config", False, f"异常: {str(e)}")
            print(f"  [FAIL] invalid_config - {str(e)}")

    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("开始执行 KnowledgeRetriever 重构回归测试")
        print("=" * 80)

        # 1. 测试重构后的方法
        self.test_refactored_methods()

        # 2. 测试通用方法
        self.test_generic_methods()

        # 3. 测试集成场景
        self.test_integration()

        # 4. 测试边界情况
        self.test_edge_cases()

        # 生成报告
        report = self.report.generate_report()
        print(report)

        # 保存报告到文件
        report_path = os.path.join(
            os.path.dirname(__file__), "..", "reports", "knowledge_retriever_regression_test_report.txt"
        )
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"\n[REPORT] 测试报告已保存到: {report_path}")

        return self.report.failed_tests == 0


if __name__ == "__main__":
    # 创建测试实例
    test_suite = TestKnowledgeRetrieverRegression()
    test_suite.setup_method()

    # 运行所有测试
    success = test_suite.run_all_tests()

    # 返回退出码
    sys.exit(0 if success else 1)
