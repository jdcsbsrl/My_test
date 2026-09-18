# 模块间协作接口文档

## 概述

本文档描述 `trae_test` 和 `auto_test` 当前的协作边界。测试用例生成和自动化执行是两条独立链路，通过用例登记表、脚本关联和运行时报告交换状态；不再通过临时 JSON 文件在两个模块之间往返传递测试用例。

## 当前架构

```text
用户需求
    │
    ▼
tools/case_generator_cli.py
    │
    ▼
CaseGenerationService
    │  KnowledgeRetriever
    │  RAG provider
    │  fixed-field policy
    ▼
AuditGateway + ReleaseQualityGate
    │
    ├── 诊断和审核结果 → .runtime/reports/
    ├── 最终 Excel → workspace/YYYYMMDD/
    └── --register → data/private/case_registry.sqlite3

用例登记表 + script_id
    │
    ▼
tools/run_regression.py
    │
    ├── ConfigManager / 环境安全校验
    ├── regression_session
    ├── 已登记 pytest 节点
    └── TestReportGenerator → .runtime/reports/
```

## 模块职责

### trae_test

负责：

- 通过 `KnowledgeRetriever` 检索业务依据；
- 根据需求和候选内容生成 15 字段测试用例；
- 运行固定字段策略、评分和格式整理；
- 通过 `AuditGateway` 和 `ReleaseQualityGate` 审核；
- 使用固定模板导出 Excel；
- 将活动版本和脚本关联登记到用例版本库。

正式入口：

```powershell
python tools/case_generator_cli.py generate --help
```

### auto_test

负责：

- 加载 `test` 或 `uat` 环境配置；
- 校验端点和执行环境安全；
- 执行已登记用例关联的 pytest 节点；
- 管理浏览器会话、数据生命周期和执行证据；
- 生成 HTML/JSON 回归报告。

正式入口：

```powershell
python tools/run_regression.py --help
```

## 生成结果契约

`CaseGenerationService.generate()` 返回一个结果字典，至少包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `ready`、`missing_knowledge`、`needs_information` 或 `generation_failed` |
| `cases` | array | 经固定字段处理和审核的候选用例 |
| `questions` | array | 需要补充的业务依据或信息 |
| `sources` | array | 本次通过知识库 API 获取的来源摘要 |
| `audit` | object | `AuditResult.to_dict()` 结果 |
| `release_decision` | object | 发布门禁结果 |

用例内容必须符合 `template_builder.ALL_FIELDS` 定义的 15 字段标准。运行时质量、规则绑定和覆盖矩阵使用 `_runtime_` 命名空间，不扩展正式 Excel 表头。

## Python 调用示例

需要在 Python 中复用生成服务时，使用当前服务和审核契约：

```python
from modules.trae_test.utils.case_generation_service import CaseGenerationService

service = CaseGenerationService()
result = service.generate(
    "验证销售订单查询的正常、异常和边界场景",
    "REQ-DEMO",
    provider="self-hosted-llm",
    priority="P1",
)

if result["status"] != "ready":
    raise RuntimeError(result.get("questions") or result.get("generation_errors"))
```

正式导出、登记和版本更新建议使用 CLI，因为 CLI 负责输出路径、运行时诊断、固定模板和登记流程：

```powershell
python tools/case_generator_cli.py generate `
  --module "销售" `
  --function "订单查询" `
  --requirement-id REQ-DEMO `
  --requirement "验证销售订单查询的正常、异常和边界场景" `
  --provider self-hosted-llm `
  --register
```

## 回归执行示例

默认只预览执行范围：

```powershell
python tools/run_regression.py --env test --scope module
python tools/run_regression.py --env test --case-id CASE-ID
python tools/run_regression.py --env test --requirement-id REQ-DEMO --impact-query "销售订单查询完整业务规则"
```

获得明确授权并确认环境后，使用 `--execute` 执行已登记脚本：

```powershell
python tools/run_regression.py --env test --case-id CASE-ID --execute
```

回归执行不会把自然语言用例自动编译为测试脚本。没有有效 `script_id` 的用例只能出现在计划或健康检查结果中，不能直接执行。

## 数据和安全边界

- 知识库只能通过 `KnowledgeRetriever` API 访问；
- 不得直接按路径读取知识库原始 JSON；
- 真实凭证和业务数据保存在被忽略的本地配置或 `data/private/`；
- 最终 Excel 只写入 `workspace/YYYYMMDD/`；
- 中间 JSON、评分轨迹、审核结果和回归报告只写入 `.runtime/`；
- `workspace/` 中的历史交付和登记表历史版本不得自动清理；
- 自动化执行只允许 `test`、`test_env` 或 `uat` 中经批准的测试端点，禁止生产环境。

## 兼容性说明

`modules/trae_test/utils/test_case_generator.py` 仍保留低层兼容接口，供历史评估和部分测试使用；它不是正式 CLI 入口，新代码应优先使用 `CaseGenerationService`。

兼容层当前按以下策略处理：

| 兼容路径 | 当前状态 | 处理方式 |
|----------|----------|----------|
| `modules/auto_test/core/environment.py` | 历史 `Environment` API，测试仍直接调用部分辅助方法 | 保留 API，但配置加载和环境安全校验统一委托 `ConfigManager` |
| `modules/auto_test/core/api_client.py` | 被 API、登录和回归模块广泛使用的旧客户端外观 | 保留外观，内部委托 `drivers/http_driver.py`；新代码优先直接使用 `HttpDriver` |
| `modules/auto_test/core/driver.py` | 历史 HTTP driver 语义，当前主要由兼容测试覆盖 | 暂不删除；迁移调用方和测试后再评估移除 |
| `modules/auto_test/core/playwright_manager.py` | 历史浏览器单上下文管理 API | 保留薄封装，内部委托 `BrowserDriver` |
| `modules/auto_test/facades/api/auth_facade.py` | API 层旧导入路径和 patch 点 | 保留兼容 facade，认证行为继承 canonical facade |

新代码应使用 `ConfigManager`、`HttpDriver`、`BrowserDriver` 和 `modules.auto_test.facades.auth_facade.AuthFacade`。

以下三个编排模块也暂时保留，但不属于当前正式入口：

| 模块 | 当前作用 | 当前调用范围 | 后续移除条件 |
|------|----------|--------------|--------------|
| `modules/trae_test/orchestrator/agent_manager.py` | Agent 知识域挂载、上下文缓存和访问统计 | Agent 管理单元测试、历史 E2E 测试 | 相关测试迁移到 `KnowledgeRetriever`/服务层，且确认无外部调用 |
| `modules/trae_test/orchestrator/auto_agent.py` | 自动化候选分析、框架建议、资源估算和方案报告 | 自动化方案单元测试、历史集成测试 | 方案分析需求迁移到当前服务或明确废弃 |
| `modules/trae_test/orchestrator/workflow_state_machine.py` | 旧生成/审核/确认状态流和超时处理 | 状态机单元测试、历史集成测试 | 相关测试迁移到当前服务与质量门禁，且确认无外部调用 |

删除前必须先迁移或删除对应测试，并再次检查仓库外调用方。当前阶段只做兼容标记，不改变上述模块的行为。
