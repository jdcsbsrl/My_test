"""AutoAgent智能体 - 自动化方案生成与影响分析"""

import time
from datetime import datetime
from enum import Enum
from typing import Any


class RiskLevel(Enum):
    """风险等级枚举"""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TestFramework(Enum):
    """测试框架枚举"""

    PLAYWRIGHT = "Playwright"
    JEST = "Jest"
    POSTMAN = "Postman"
    CYPRESS = "Cypress"
    SELENIUM = "Selenium"


class AutoAgent:
    """自动化测试方案生成智能体"""

    def __init__(self):
        self.case_analysis_cache = {}

    def analyze_cases(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        """分析测试用例，确定自动化方案"""
        start_time = time.time()

        analysis = {
            "total_cases": len(cases),
            "auto_candidate_count": 0,
            "manual_only_count": 0,
            "framework_recommendations": [],
            "estimated_execution_time_minutes": 0,
            "external_dependencies": [],
            "resource_requirements": {},
        }

        auto_candidates = []
        manual_only = []

        for case in cases:
            case_type = case.get("用例类型", "功能测试")
            priority = case.get("优先级", "P3")

            # 判断是否适合自动化
            if self._is_automation_candidate(case):
                auto_candidates.append(case)
                # 估算执行时间（按用例步骤数量）
                steps = case.get("测试步骤", "")
                step_count = len([s for s in steps.split("\n") if s.strip()])
                analysis["estimated_execution_time_minutes"] += step_count * 0.5

            else:
                manual_only.append(case)

        analysis["auto_candidate_count"] = len(auto_candidates)
        analysis["manual_only_count"] = len(manual_only)

        # 推荐测试框架
        analysis["framework_recommendations"] = self._recommend_frameworks(auto_candidates)

        # 识别外部依赖
        analysis["external_dependencies"] = self._identify_dependencies(auto_candidates)

        # 估算资源需求
        analysis["resource_requirements"] = self._estimate_resources(len(auto_candidates))

        analysis["analysis_time_ms"] = (time.time() - start_time) * 1000

        return analysis

    def _is_automation_candidate(self, case: dict[str, Any]) -> bool:
        """判断用例是否适合自动化"""
        case_type = case.get("用例类型", "")

        # UI自动化候选
        if case_type in ["功能测试", "回归测试", "接口测试"]:
            return True

        # 性能测试通常需要特殊处理
        if case_type == "性能测试":
            return False

        # 探索性测试不适合自动化
        if case_type == "探索性测试":
            return False

        return True

    def _recommend_frameworks(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """根据用例类型推荐测试框架"""
        recommendations = []
        framework_counts = {}

        for case in cases:
            case_type = case.get("用例类型", "功能测试")

            if case_type in ["功能测试", "回归测试"]:
                framework_counts["Playwright"] = framework_counts.get("Playwright", 0) + 1

            elif case_type == "接口测试":
                framework_counts["Postman"] = framework_counts.get("Postman", 0) + 1

            elif case_type == "单元测试":
                framework_counts["Jest"] = framework_counts.get("Jest", 0) + 1

        # 按优先级排序推荐
        for framework, count in sorted(framework_counts.items(), key=lambda x: -x[1]):
            recommendations.append(
                {
                    "framework": framework,
                    "applicable_case_count": count,
                    "recommendation_level": "HIGH" if count > 5 else "MEDIUM",
                }
            )

        return recommendations

    def _identify_dependencies(self, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """识别外部依赖"""
        dependencies = {}

        for case in cases:
            # 从测试步骤中提取可能的依赖
            steps = case.get("测试步骤", "")

            # 识别API依赖
            if "API" in steps or "接口" in steps:
                dependencies["api_service"] = {"type": "API服务", "description": "后端API接口", "mock_required": True}

            # 识别数据库依赖
            if "数据库" in steps or "查询" in steps:
                dependencies["database"] = {"type": "数据库", "description": "业务数据库", "mock_required": False}

            # 识别外部系统依赖
            if "支付" in steps or "短信" in steps or "邮件" in steps:
                dependencies["external_services"] = {
                    "type": "外部服务",
                    "description": "支付网关、短信服务、邮件服务",
                    "mock_required": True,
                }

        return list(dependencies.values())

    def _estimate_resources(self, case_count: int) -> dict[str, Any]:
        """估算资源需求"""
        return {
            "cpu_cores": max(2, min(8, case_count // 10)),
            "memory_gb": max(4, min(16, case_count // 5)),
            "storage_gb": max(2, case_count // 20),
            "network_bandwidth_mbps": 100,
        }

    def generate_solution(self, workflow_id: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
        """生成自动化测试方案"""
        start_time = time.time()

        analysis = self.analyze_cases(cases)

        solution = {
            "workflow_id": workflow_id,
            "generated_at": datetime.now().isoformat(),
            "analysis": analysis,
            "framework_plan": self._generate_framework_plan(analysis),
            "directory_structure": self._generate_directory_structure(analysis),
            "external_dependencies": analysis["external_dependencies"],
            "execution_environment": self._generate_execution_environment(analysis),
            "estimated_execution_time_minutes": analysis["estimated_execution_time_minutes"],
            "mock_strategy": self._generate_mock_strategy(analysis),
            "risk_assessment": self._perform_risk_assessment(cases),
            "generation_time_ms": (time.time() - start_time) * 1000,
        }

        return solution

    def _generate_framework_plan(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """生成框架使用计划"""
        plan = {"primary_framework": "", "secondary_frameworks": [], "version_recommendations": {}}

        if analysis["framework_recommendations"]:
            plan["primary_framework"] = analysis["framework_recommendations"][0]["framework"]
            plan["secondary_frameworks"] = [fw["framework"] for fw in analysis["framework_recommendations"][1:]]

        # 添加版本建议
        plan["version_recommendations"] = {"Playwright": ">=1.30.0", "Jest": ">=29.0.0", "Postman": ">=10.0.0"}

        return plan

    def _generate_directory_structure(self, analysis: dict[str, Any]) -> str:
        """生成目录结构说明"""
        structure = """自动化测试脚本目录结构:
├── tests/                              # 测试根目录
│   ├── e2e/                           # E2E测试
│   │   ├── pages/                     # 页面对象模型(POM)
│   │   │   ├── BasePage.py
│   │   │   └── SalesOrderPage.py
│   │   ├── specs/                      # 测试用例
│   │   │   └── sales_order.spec.ts
│   │   └── utils/                     # 工具函数
│   ├── api/                            # API测试
│   │   └── sales_order_api.test.js
│   ├── unit/                           # 单元测试
│   ├── fixtures/                       # 测试数据
│   │   └── test_data.json
│   └── .runtime/reports/                        # 测试报告
├── config/                             # 配置文件
│   ├── playwright.config.js
│   └── jest.config.js
├── mock/                               # Mock服务
│   └── api_mocks.js
└── package.json                        # 依赖配置
"""
        return structure

    def _generate_execution_environment(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """生成执行环境要求"""
        resources = analysis["resource_requirements"]

        return {
            "hardware": {
                "cpu": f"{resources['cpu_cores']} cores",
                "memory": f"{resources['memory_gb']} GB RAM",
                "storage": f"{resources['storage_gb']} GB",
            },
            "software": {
                "node_version": ">=18.0.0",
                "npm_version": ">=8.0.0",
                "python_version": ">=3.8.0",
                "browser_version": {"Chrome": ">=90.0.0", "Firefox": ">=88.0.0"},
            },
            "network": {
                "bandwidth": f"{resources['network_bandwidth_mbps']} Mbps",
                "access_required": ["ERP系统", "测试数据库", "Mock服务"],
            },
        }

    def _generate_mock_strategy(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """生成Mock策略"""
        strategies = []

        for dep in analysis["external_dependencies"]:
            if dep.get("mock_required"):
                strategies.append(
                    {
                        "dependency_type": dep["type"],
                        "description": dep["description"],
                        "mock_tool": "MockServiceWorker" if dep["type"] == "API服务" else "WireMock",
                        "mock_data_required": True,
                    }
                )

        return strategies

    def _perform_risk_assessment(self, cases: list[dict[str, Any]]) -> dict[str, Any]:
        """执行影响分析"""
        risks = []

        for case in cases:
            risk_level = RiskLevel.LOW
            risk_description = ""
            affected_data = []

            steps = case.get("测试步骤", "")
            expected = case.get("预期结果", "")

            # 高风险：涉及数据修改/删除
            if "删除" in steps or "修改" in steps or "更新" in steps:
                risk_level = RiskLevel.HIGH
                risk_description = "测试用例涉及数据修改操作，可能影响生产数据"
                affected_data = ["订单数据", "用户数据"]

            # 中风险：涉及支付或财务操作
            elif "支付" in steps or "金额" in steps or "结算" in steps:
                risk_level = RiskLevel.MEDIUM
                risk_description = "测试用例涉及支付/财务操作，需要特别注意"
                affected_data = ["支付记录", "财务数据"]

            # 低风险：查询类操作
            elif "查询" in steps or "查看" in steps:
                risk_level = RiskLevel.LOW
                risk_description = "仅涉及数据查询，风险较低"

            if risk_level != RiskLevel.LOW or affected_data:
                risks.append(
                    {
                        "case_id": case.get("用例编号", ""),
                        "case_name": case.get("用例名称", ""),
                        "risk_level": risk_level.value,
                        "risk_description": risk_description,
                        "affected_data": affected_data,
                        "suggestion": self._get_risk_suggestion(risk_level),
                    }
                )

        return {
            "total_risks": len(risks),
            "high_risk_count": sum(1 for r in risks if r["risk_level"] == "HIGH"),
            "medium_risk_count": sum(1 for r in risks if r["risk_level"] == "MEDIUM"),
            "low_risk_count": sum(1 for r in risks if r["risk_level"] == "LOW"),
            "risks": risks,
        }

    def _get_risk_suggestion(self, risk_level: RiskLevel) -> str:
        """根据风险等级返回建议"""
        suggestions = {
            RiskLevel.HIGH: "建议在隔离环境执行，执行前备份数据，安排专人监控",
            RiskLevel.MEDIUM: "建议在测试环境执行，确保有回滚方案",
            RiskLevel.LOW: "正常执行即可，无需特殊处理",
        }
        return suggestions.get(risk_level, "")

    def generate_markdown_report(self, solution: dict[str, Any]) -> str:
        """生成Markdown格式的方案报告"""
        report = f"""# 自动化测试方案报告

## 1. 基本信息

| 项目 | 内容 |
|------|------|
| 工作流ID | {solution['workflow_id']} |
| 生成时间 | {solution['generated_at']} |
| 生成耗时 | {solution['generation_time_ms']:.2f} ms |

## 2. 用例分析

### 2.1 用例统计

| 类别 | 数量 |
|------|------|
| 总用例数 | {solution['analysis']['total_cases']} |
| 可自动化 | {solution['analysis']['auto_candidate_count']} |
| 仅手动 | {solution['analysis']['manual_only_count']} |
| 预计执行时间 | {solution['analysis']['estimated_execution_time_minutes']} 分钟 |

### 2.2 框架推荐

"""

        # 添加框架推荐
        if solution["framework_plan"]["primary_framework"]:
            report += f"- **{solution['framework_plan']['primary_framework']}**: 主框架\n"

        for fw in solution["framework_plan"]["secondary_frameworks"]:
            report += f"- **{fw}**: 次要框架\n"

        report += f"""

## 3. 目录结构

```
{solution['directory_structure']}
```

## 4. 外部依赖

"""

        for dep in solution["external_dependencies"]:
            report += f"- **{dep['type']}**: {dep['description']} (需Mock: {dep['mock_required']})\n"

        report += f"""

## 5. 执行环境要求

### 5.1 硬件配置

| 资源 | 要求 |
|------|------|
| CPU | {solution['execution_environment']['hardware']['cpu']} |
| 内存 | {solution['execution_environment']['hardware']['memory']} |
| 存储 | {solution['execution_environment']['hardware']['storage']} |

### 5.2 软件配置

| 软件 | 版本要求 |
|------|----------|
| Node.js | {solution['execution_environment']['software']['node_version']} |
| Python | {solution['execution_environment']['software']['python_version']} |

## 6. 影响分析

### 6.1 风险统计

| 风险等级 | 数量 |
|----------|------|
| 🔴 高风险 | {solution['risk_assessment']['high_risk_count']} |
| 🟡 中风险 | {solution['risk_assessment']['medium_risk_count']} |
| 🟢 低风险 | {solution['risk_assessment']['low_risk_count']} |

### 6.2 风险详情

"""

        for risk in solution["risk_assessment"]["risks"]:
            level_icon = "🔴" if risk["risk_level"] == "HIGH" else "🟡" if risk["risk_level"] == "MEDIUM" else "🟢"
            report += f"""#### {level_icon} {risk['case_name']}

- **用例编号**: {risk['case_id']}
- **风险等级**: {risk['risk_level']}
- **风险描述**: {risk['risk_description']}
- **影响数据**: {', '.join(risk['affected_data'])}
- **建议**: {risk['suggestion']}

"""

        report += """## 7. Mock策略

| 依赖类型 | Mock工具 | 需要Mock数据 |
|----------|----------|--------------|
"""

        for strategy in solution["mock_strategy"]:
            report += (
                f"| {strategy['dependency_type']} | {strategy['mock_tool']} | {strategy['mock_data_required']} |\n"
            )

        return report


class ConfirmationService:
    """二次确认服务"""

    def __init__(self):
        self.confirmations = {}  # workflow_id -> confirmation_info

    def confirm_solution(self, workflow_id: str, confirmed: bool, comment: str = "") -> dict[str, Any]:
        """确认自动化方案"""
        self.confirmations[workflow_id] = {
            "confirmed": confirmed,
            "comment": comment,
            "confirmed_at": datetime.now().isoformat(),
            "status": "approved" if confirmed else "rejected",
        }

        return {
            "success": True,
            "workflow_id": workflow_id,
            "confirmed": confirmed,
            "comment": comment,
            "message": "方案已" + ("同意" if confirmed else "拒绝"),
        }

    def get_confirmation(self, workflow_id: str) -> dict[str, Any] | None:
        """获取确认状态"""
        return self.confirmations.get(workflow_id)

    def reset_confirmation(self, workflow_id: str):
        """重置确认状态"""
        if workflow_id in self.confirmations:
            del self.confirmations[workflow_id]


# 全局实例
auto_agent = AutoAgent()
confirmation_service = ConfirmationService()


if __name__ == "__main__":
    # 测试AutoAgent
    test_cases = [
        {
            "用例编号": "TC-001",
            "用例名称": "验证订单创建",
            "用例类型": "功能测试",
            "优先级": "P1",
            "测试步骤": "1. 进入订单页面\n2. 填写订单信息\n3. 点击提交",
            "预期结果": "订单创建成功",
        },
        {
            "用例编号": "TC-002",
            "用例名称": "验证订单删除",
            "用例类型": "功能测试",
            "优先级": "P1",
            "测试步骤": "1. 选择订单\n2. 点击删除\n3. 确认删除",
            "预期结果": "订单删除成功",
        },
        {
            "用例编号": "TC-003",
            "用例名称": "验证订单支付",
            "用例类型": "功能测试",
            "优先级": "P0",
            "测试步骤": "1. 选择待支付订单\n2. 点击支付\n3. 完成支付",
            "预期结果": "支付成功",
        },
    ]

    agent = AutoAgent()
    solution = agent.generate_solution("test_wf_001", test_cases)

    print("方案生成成功！")
    print(f"生成耗时: {solution['generation_time_ms']:.2f} ms")
    print(f"可自动化用例: {solution['analysis']['auto_candidate_count']}")
    print(f"高风险用例: {solution['risk_assessment']['high_risk_count']}")

    # 生成报告
    report = agent.generate_markdown_report(solution)
    from modules.trae_test.utils.runtime_paths import runtime_dir

    report_path = runtime_dir("reports") / "auto_solution_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已保存至 {report_path}")
