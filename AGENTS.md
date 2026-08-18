# Test ERP Agent Workspace Index

## 2026-07-24 本地知识库索引增补（Agent 必读）

> 真实知识库默认保留在本地 `assets/knowledge_base/`，不上传 GitHub。提交仓库时只提交工具代码、流程文档和脱敏样例，避免泄露业务规则、测试数据、订单号、SKU、账号、环境信息等敏感内容。

### 本地知识库入口

| 索引项 | 位置 | 用途 |
|-------|------|------|
| 本地知识库使用指南 | [docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md](docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md) | 本地知识库目录、隐私边界、推荐知识格式、lint/migrate/validate 流程 |
| 知识库更新工作流 | [docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md](docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md) | 标准化更新流程 |
| 知识库管理器 | [tools/kb_manager.py](tools/kb_manager.py) | `lint` / `migrate` / `process` / `scan` / `validate` |
| 检索 API | [modules/trae_test/utils/knowledge_retriever.py](modules/trae_test/utils/knowledge_retriever.py) | Agent 访问知识库的统一入口 |

### Agent 更新知识库时必须使用的流程

```bash
python tools/kb_manager.py lint --file path/to/source.json
python tools/kb_manager.py migrate --source path/to/source.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword
```

更新已有知识文件时：

```bash
python tools/kb_manager.py lint --file assets/knowledge_base/data/original/file_title.json
python tools/kb_manager.py process --file assets/knowledge_base/data/original/file_title.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword
```

### Agent 检索知识库时必须遵守

- 使用 `KnowledgeRetriever` API，不直接读取 `assets/knowledge_base/data/original/*.json`。
- 检索前如 registry 缺失或疑似过期，调用 `r.refresh_registry()`；当前实现会在 registry 缺失时自动重建。
- 优先使用 `retrieve()` / `search_business_rules()` 获取精准片段。
- 只有用户明确要求全量分析时，才使用 `get_all_chunks()`，并设置 `max_chunks`。

**文档版本**: 3.2.0  
**知识库 API 版本**: 3.0.0  
**架构**: HarnessEngineer  
**最近审查时间**: 2026-07-27

---

## 🎯 查询指引

> **重要**: 请根据任务类型精准定位所需索引，避免全量查询。

| 任务类型 | 索引位置 | 入口方式 |
|---------|---------|---------|
| 测试用例生成 | [任务类型索引 → 测试用例生成](#测试用例生成) | TRAE_TEST_WORKFLOW.md |
| 自动化测试执行 | [任务类型索引 → 自动化测试](#自动化测试) | AUTO_TEST_WORKFLOW.md |
| 代码审核 | [任务类型索引 → 代码审核](#代码审核) | agent_rules.md |
| 知识检索 | [任务类型索引 → 知识检索](#知识检索) | **KnowledgeRetriever API（见下文）** |
| **知识库更新** | **[任务类型索引 → 知识库更新](#知识库更新)** | **KNOWLEDGE_BASE_UPDATE_WORKFLOW.md** |
| 环境配置 | [任务类型索引 → 环境配置](#环境配置) | VIRTUAL_ENV.md |

---

## 🔴 核心规则

1. **环境红线**: 自动化测试仅允许在 UAT/内网测试环境执行
2. **模块分工**: trae_test(用例生成) / auto_test(测试执行)
3. **测试执行**: 需用户明确批准
4. **知识访问**: **必须通过 `KnowledgeRetriever` API 访问知识库，禁止直接按文件路径读取原始JSON**
5. **全能审核**: 所有任务必须经 AuditAgent 审核
6. **索引刷新**: 每次执行知识检索任务前，若距离上次检索超过1小时，或遇到 FileNotFoundError，需调用 `r.refresh_registry()` 刷新注册表，确保索引与物理文件一致

---

## 📦 知识库 v3.0 速查（Agent 必读）

> **Agent 应始终通过 Python API 访问知识库，不要依赖直接文件路径读取。**

```python
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
r = KnowledgeRetriever()
r.retrieve("销售")              # 自动路由检索（推荐）
r.search_business_rules("订单")  # 业务规则关键词检索
r.search_requirements("日志")    # 需求清单关键词检索
r.get_all_chunks("销售模块")     # 按chunk分批加载大文件
```

**异常处理与 Fallback 机制**：

```python
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

r = KnowledgeRetriever()

try:
    result = r.retrieve("销售订单")
    if not result:
        # Fallback: 检索为空时尝试其他检索方式
        result = r.search_business_rules("销售订单")
    if not result:
        # 最终 Fallback: 返回空结果或提示用户
        print("未检索到相关知识，请尝试其他关键词")
except Exception as e:
    # API 报错处理：记录日志并刷新注册表重试
    print(f"检索失败: {e}")
    r.refresh_registry()
    result = r.retrieve("销售订单")
```

**上下文窗口管理规则**：

| 规则 | 说明 |
|------|------|
| 优先精准检索 | 优先使用 `retrieve()` 或 `search_business_rules()` 获取精准片段 |
| 限制全量加载 | 仅在用户明确要求全量分析时，才使用 `get_all_chunks()`，且必须配合 `max_chunks` 参数（建议 `max_chunks=5`） |
| 按需加载 | 使用 `get_chunk_by_id()` 按需加载单个 chunk，避免一次性注入大量内容 |

**v3.0 存储架构**：
```
assets/knowledge_base/
├── data/original/    ← 原始JSON+MD（数量以 registry/API 为准） → 直接文件路径可能变化，勿硬编码
├── data/chunks/      ← 分块文件（>80KB自动切）                 → 通过 get_all_chunks() 读取
├── index/global/     ← v3.0 全局索引               → 通过 get_index() 读取
├── index/inverted/   ← 倒排索引（关键词数量以索引元数据为准） → 通过 search_by_inverted_index() 读取
└── metadata/         ← 文件注册表（Tag映射）        → 通过 refresh_registry() / list_available_files() / get_retrieval_stats() 间接访问状态
```

---

## 📋 任务类型索引

### 测试用例生成

| 索引项 | 文档位置 | 用途 |
|-------|---------|------|
| 工作流程 | [docs/TRAE_TEST_WORKFLOW.md](docs/TRAE_TEST_WORKFLOW.md) | 测试用例生成完整流程（含质量评分/优化/重生闭环） |
| 用例生成器 | [modules/trae_test/utils/test_case_generator.py](modules/trae_test/utils/test_case_generator.py) | 15字段标准格式生成；字段顺序以 `docs/TRAE_TEST_WORKFLOW.md` 的 Excel 表头规范为准 |
| 知识检索 | [modules/trae_test/utils/knowledge_retriever.py](modules/trae_test/utils/knowledge_retriever.py) | 知识库检索工具 |
| Excel生成 | [modules/trae_test/utils/excel_generator.py](modules/trae_test/utils/excel_generator.py) | 统一Excel文件生成 |
| CLI工具 | [tools/case_generator_cli.py](tools/case_generator_cli.py) | 命令行用例生成 |
| **质量评分引擎** | [modules/trae_test/utils/test_case_strategy.py](modules/trae_test/utils/test_case_strategy.py) | **TestCaseScoreEngine: 五维度评分 + 冷启动保护** |
| **用例优化器** | [modules/trae_test/utils/test_case_strategy.py](modules/trae_test/utils/test_case_strategy.py) | **TestCaseOptimizer: 自动优化步骤/预期/名称** |
| **自动重生闭环** | [modules/trae_test/utils/test_case_strategy.py](modules/trae_test/utils/test_case_strategy.py) | **TestCaseRegenerationLoop: 重生闭环 + 熔断机制** |

### 自动化测试

| 索引项 | 文档位置 | 用途 |
|-------|---------|------|
| 工作流程 | [docs/AUTO_TEST_WORKFLOW.md](docs/AUTO_TEST_WORKFLOW.md) | 自动化测试执行流程（含数据生命周期管理） |
| 环境配置 | [modules/auto_test/core/environment.py](modules/auto_test/core/environment.py) | 环境配置管理 |
| 页面对象 | [modules/auto_test/pages/](modules/auto_test/pages/) | UI页面对象模型 |
| API封装 | [modules/auto_test/api/](modules/auto_test/api/) | API接口封装 |
| 驱动层 | [modules/auto_test/drivers/](modules/auto_test/drivers/) | 浏览器/HTTP驱动 |
| **数据工厂** | [modules/auto_test/core/test_data_factory.py](modules/auto_test/core/test_data_factory.py) | **TestDataFactory: 统一数据工厂入口** |
| **数据加载器** | [modules/auto_test/core/test_data_factory.py](modules/auto_test/core/test_data_factory.py) | **DataLoader: 多格式文件加载（JSON/YAML/CSV/Excel）+ 懒加载** |
| **动态数据生成** | [modules/auto_test/core/test_data_factory.py](modules/auto_test/core/test_data_factory.py) | **DynamicDataGenerator: 带缓存的动态数据生成** |
| **数据版本管理** | [modules/auto_test/core/test_data_factory.py](modules/auto_test/core/test_data_factory.py) | **DataVersionManager: 测试数据文件版本控制** |
| **生命周期管理** | [modules/auto_test/core/test_data_lifecycle.py](modules/auto_test/core/test_data_lifecycle.py) | **TestDataLifecycleManager: 拓扑排序setUp + 级联cleanup + DB兜底** |

### 代码审核

| 索引项 | 文档位置 | 用途 |
|-------|---------|------|
| Agent规则 | [docs/AGENT_RULES.md](docs/AGENT_RULES.md) | 智能体配置与交互规则 |
| 审核Agent | [modules/trae_test/orchestrator/audit_agent_enhanced.py](modules/trae_test/orchestrator/audit_agent_enhanced.py) | 全能实时审核系统 |
| 编码规范 | [docs/CODING_RULES.md](docs/CODING_RULES.md) | 代码编写规范 |
| 项目规则 | [docs/PROJECT_RULES.md](docs/PROJECT_RULES.md) | 项目执行规则 |

### 知识检索

> **Agent 访问知识库的唯一入口是 `KnowledgeRetriever`，禁止直接按文件路径读取。**

| 索引项 | 文档位置 | 用途 |
|-------|---------|------|
| **检索 API（入口）** | [modules/trae_test/utils/knowledge_retriever.py](modules/trae_test/utils/knowledge_retriever.py) | **Agent 唯一访问入口** |
| 知识库全局索引 | [assets/knowledge_base/index/global/global_index.json](assets/knowledge_base/index/global/global_index.json) | v3.0 全局索引；仅供维护工具/状态核查使用 |
| 文件注册表 | [assets/knowledge_base/metadata/file_registry.json](assets/knowledge_base/metadata/file_registry.json) | Tag→File 映射；Agent 检索必须走 API |
| 倒排索引 | [assets/knowledge_base/index/inverted/inverted_index.json](assets/knowledge_base/index/inverted/inverted_index.json) | 关键词检索底层索引；Agent 检索必须走 API |
| 更新工作流程 | [docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md](docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md) | 知识库更新标准化流程 |
| 检索使用指南 | [docs/KNOWLEDGE_BASE_RETRIEVER.md](docs/KNOWLEDGE_BASE_RETRIEVER.md) | 智能检索系统使用说明 |

> **注意**: 业务数据文件列表应通过 `r.get_index()` 或 `r.list_available_files()` 动态获取，禁止在系统提示词中硬编码具体文件清单。

### 知识库更新

| 索引项 | 文档位置 | 用途 |
|-------|---------|------|
| 更新工作流程 | [docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md](docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md) | 标准化更新流程（四阶段） |
| 知识库管理器 | [tools/kb_manager.py](tools/kb_manager.py) | CLI管理工具（scan / process / migrate） |
| 文件分割器 | [modules/trae_test/utils/file_splitter.py](modules/trae_test/utils/file_splitter.py) | >80KB自动语义分割（SHA256验证） |
| 索引构建器 | [modules/trae_test/utils/index_builder_v3.py](modules/trae_test/utils/index_builder_v3.py) | TF-IDF关键词 + 三层索引 |
| 变更监控器 | [modules/trae_test/utils/kb_monitor.py](modules/trae_test/utils/kb_monitor.py) | 文件大小检测 + 自动触发处理 |
| 完整性验证 | [tools/verify_knowledge_base.py](tools/verify_knowledge_base.py) | SHA256哈希 + 分块重建校验 |
| 检索系统 | [modules/trae_test/utils/knowledge_retriever.py](modules/trae_test/utils/knowledge_retriever.py) | 智能检索API（Agent入口） |

### 环境配置

| 索引项 | 文档位置 | 用途 |
|-------|---------|------|
| 虚拟环境 | [docs/VIRTUAL_ENV.md](docs/VIRTUAL_ENV.md) | 虚拟环境详细说明 |
| 环境配置 | [configs/](configs/) | 配置文件目录 |
| 测试配置 | [modules/auto_test/configs/](modules/auto_test/configs/) | 自动化测试常量/模块内配置代码 |

---

## 🧠 智能体索引

| 智能体 | 职责 | 触发条件 | 核心入口 |
|-------|------|----------|----------|
| TestCaseGenerator | 测试用例生成 | 用户提交测试需求 | [test_case_generator.py](modules/trae_test/utils/test_case_generator.py) |
| AutoTestExecutor | 自动化测试执行 | 测试用例生成完成 | [AUTO_TEST_WORKFLOW.md](docs/AUTO_TEST_WORKFLOW.md) / [run_regression.py](tools/run_regression.py) |
| KnowledgeRetriever | 知识检索 | 其他智能体请求检索 | [knowledge_retriever.py](modules/trae_test/utils/knowledge_retriever.py) |
| TestReportGenerator | 报告生成 | 测试执行完成 | [report_generator.py](tools/report_generator.py) |
| **AuditAgent** | **全能审核（阻塞式网关）** | 任何任务输出交付给用户前（拦截器/网关） | [audit_agent_enhanced.py](modules/trae_test/orchestrator/audit_agent_enhanced.py) |

> **协同编排入口**: [multi_agent_runner.py](tools/multi_agent_runner.py) - 多Agent协同编排统一入口

---

## 📚 文档索引

| 文档 | 位置 | 用途 |
|------|------|------|
| 项目说明 | [README.md](README.md) | 项目介绍 |
| 架构设计 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构说明 |
| 项目结构 | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | 目录结构 |
| 工作流程 | [docs/WORKFLOW.md](docs/WORKFLOW.md) | 整体流程 |
| 虚拟环境 | [docs/VIRTUAL_ENV.md](docs/VIRTUAL_ENV.md) | 环境配置 |
| 使用示例 | [docs/USAGE_EXAMPLES.md](docs/USAGE_EXAMPLES.md) | 命令示例 |

---

## 🛠️ 工具索引

| 工具 | 位置 | 用途 |
|------|------|------|
| 多Agent运行器 | [tools/multi_agent_runner.py](tools/multi_agent_runner.py) | 统一入口 |
| 项目结构审核 | [tools/project_structure_auditor.py](tools/project_structure_auditor.py) | 架构验证 |
| 用例生成CLI | [tools/case_generator_cli.py](tools/case_generator_cli.py) | 命令行工具 |
| 报告生成 | [tools/report_generator.py](tools/report_generator.py) | 测试报告 |

---

## 📊 模块索引

| 模块 | 位置 | 职责 |
|------|------|------|
| trae_test | [modules/trae_test/](modules/trae_test/) | 测试用例生成 |
| auto_test | [modules/auto_test/](modules/auto_test/) | 自动化测试执行 |
| orchestrator | [modules/trae_test/orchestrator/](modules/trae_test/orchestrator/) | 多Agent协同编排 |

---

## 🔗 完整索引

- **Agent配置索引**: 已移除 Trae 专属索引；通用规则见 `docs/AGENT_RULES.md`
- **知识库全局索引**: [assets/knowledge_base/index/global/global_index.json](assets/knowledge_base/index/global/global_index.json)
- **文件注册表**: [assets/knowledge_base/metadata/file_registry.json](assets/knowledge_base/metadata/file_registry.json)
