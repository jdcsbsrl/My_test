# 项目结构规范

> 版本 2.0.0 · 2026/7/16 · 基于 HarnessEngineer 架构

---

## 一、目录结构概览

```
test_erp/
├── .trae/                    # AI智能体配置
│   ├── agents/              # 智能体定义
│   ├── documents/           # 智能体协作文档
│   ├── rules/               # 项目规则
│   └── specs/               # 规格文档
├── assets/                   # 资源文件
│   ├── knowledge_base/       # 知识库（v3.0架构）
│   │   ├── data/            # 数据存储
│   │   │   ├── original/    # 原始JSON文件
│   │   │   └── chunks/      # 分割块
│   │   ├── index/           # 索引文件
│   │   └── metadata/        # 元数据管理
│   └── templates/           # 测试用例模板
├── configs/                  # 配置文件（统一）
├── data/                     # 测试数据
├── docs/                     # 项目文档
├── fixtures/                 # Pytest插件
├── modules/                  # 核心模块
├── testcases/                # 测试用例
├── tools/                    # 工具脚本
├── utils/                    # 公共工具
└── [配置文件]               # 项目根目录配置文件
```

---

## 二、核心模块 (modules/)

### 2.1 trae_test/ - 测试用例生成模块

**职责**: 负责测试用例的生成、管理、导出等功能

```
modules/trae_test/
├── core/                     # 核心组件（新增）
│   ├── migration/              # 数据库迁移
│   │   ├── init_db.py            # 初始化数据库
│   │   ├── migrator.py           # 迁移管理器
│   │   └── schema.py             # 数据库schema
│   ├── cache_manager.py         # 缓存管理
│   └── db_pool.py               # 数据库连接池
├── orchestrator/             # 多Agent协同编排
│   ├── agent_orchestrator.py    # Agent编排器
│   ├── agent_manager.py         # Agent管理器（新增）
│   ├── auto_agent.py            # 自动Agent（新增）
│   ├── audit_agent_enhanced.py  # 全能审核Agent
│   ├── config.py                # 配置类
│   ├── exception_handler.py      # 异常处理
│   ├── monitor.py               # 监控报告
│   ├── retry_manager.py          # 重试管理
│   ├── workflow_manager.py       # 工作流管理
│   └── workflow_state_machine.py # 工作流状态机（新增）
└── utils/                    # 工具函数
    ├── excel_generator.py        # Excel生成器
    ├── knowledge_retriever.py    # 知识检索（v3.0）
    ├── test_case_generator.py     # 用例生成
    ├── test_case_strategy.py      # 用例策略引擎（新增）
    ├── test_case_style_formatter.py # 用例格式化（新增）
    ├── workspace_manager.py       # 工作区管理
    ├── business_rule_extractor.py # 业务规则抽取（新增）
    ├── business_rule_parser.py   # 业务规则解析（新增）
    ├── dir_validator.py          # 目录验证（新增）
    ├── file_management_service.py # 文件管理服务（新增）
    ├── file_repository.py        # 文件仓库（新增）
    ├── file_splitter.py          # 文件分割器（新增）
    ├── hash_utils.py             # 哈希工具（新增）
    ├── index_builder_v3.py       # 索引构建器（新增）
    ├── kb_monitor.py             # 知识库监控（新增）
    ├── metadata_manager.py       # 元数据管理（新增）
    ├── metadata_repository.py    # 元数据仓库（新增）
    ├── path_utils.py             # 路径工具（新增）
    └── template_builder.py       # 模板构建器（新增）
```

### 2.2 auto_test/ - 自动化测试执行模块

**职责**: 负责测试脚本的执行、环境配置、结果收集

```
modules/auto_test/
├── api/                     # API封装
│   ├── auth_api.py              # 认证API
│   ├── base_api.py              # 基础API
│   ├── customer_api_client.py   # 客户API客户端
│   ├── customer_api_resource.py # 客户API资源
│   └── openapi_client.py        # OpenAPI客户端
├── configs/                 # 环境配置
│   └── test_constants.py        # 测试常量
├── core/                    # 核心组件
│   ├── environment.py           # 环境配置管理
│   ├── logger.py                # 日志管理
│   ├── test_data_factory.py     # 测试数据工厂（新增）
│   ├── test_data_lifecycle.py   # 测试数据生命周期（新增）
│   ├── api_client.py            # API客户端
│   ├── auth_engine.py           # 认证引擎
│   ├── config_manager.py        # 配置管理
│   ├── db_helper.py             # 数据库助手
│   ├── driver.py                # 驱动管理
│   ├── exception_handler.py     # 异常处理
│   ├── execution_auth.py        # 执行认证
│   ├── login_service.py         # 登录服务
│   ├── playwright_manager.py    # Playwright管理
│   ├── secret_manager.py        # 密钥管理
│   ├── session_probe.py         # 会话探测
│   ├── token_manager.py         # Token管理
│   └── ...                     # 其他核心组件
├── drivers/                 # 驱动
│   ├── browser_driver.py        # 浏览器驱动
│   └── http_driver.py           # HTTP驱动
├── facades/                 # 业务逻辑封装
│   ├── auth_facade.py           # 认证门面
│   ├── inventory_sku_facade.py  # 库存SKU门面
│   └── sales_order_facade.py    # 销售订单门面
├── pages/                   # 页面对象
│   ├── login_page.py            # 登录页
│   ├── sales_order_page.py      # 销售订单页
│   ├── sales_order_export_page.py # 销售订单导出页
│   ├── inventory_sku_page.py    # 库存SKU页
│   ├── inventory_export_page.py # 库存导出页
│   ├── export_page.py           # 导出页
│   ├── sku_search_page.py       # SKU搜索页
│   └── base_page.py             # 基础页
├── reporting/               # 测试报告
│   └── allure_http.py           # Allure HTTP报告
└── tests/                   # 测试脚本（新增）
    ├── test_login_regression.py     # 登录回归测试
    ├── test_sales_order_export_sort.py # 销售订单导出排序
    ├── test_inventory_sku_system.py   # 库存SKU系统测试
    └── ...                         # 其他测试脚本
```

---

## 三、工具目录 (tools/)

### 3.1 目录规范

- 所有工具脚本直接放在 `tools/` 根目录
- 禁止创建子目录（保持扁平结构）
- 使用 snake_case 命名法

### 3.2 工具分类

| 类型 | 文件命名模式 | 示例 |
|------|-------------|------|
| 用例生成 | `generate_*.py` | `generate_cases.py` |
| 执行运行 | `run_*.py` | `run_regression.py` |
| 辅助工具 | `*_helper.py` | - |
| CLI工具 | `*_cli.py` | `case_generator_cli.py` |
| 审核工具 | `*_auditor.py` | `project_structure_auditor.py` |

---

## 四、配置目录 (configs/)

### 4.1 目录规范

- 所有配置文件统一放在 `configs/`
- 不使用 `config/` 或其他名称的目录

### 4.2 配置文件

| 文件 | 用途 |
|------|------|
| env_config.example.json | 环境配置模板 |
| env_config.example.yaml | YAML格式环境配置 |
| test.yaml | 测试环境配置 |
| uat.yaml | UAT环境配置 |
| test_env.yaml | 专用测试栈配置 |

---

## 五、命名规范

### 5.1 Python文件

- 使用 snake_case：`test_case_generator.py`
- 模块级常量使用 UPPER_CASE
- 类名使用 PascalCase
- 函数名使用 snake_case

### 5.2 目录名

- 使用 snake_case
- 使用英文
- 避免中英混用

### 5.3 避免的命名

- ❌ `测试用例模板.xlsx` → ✅ `test_case_template.xlsx`
- ❌ `工具脚本/` → ✅ `tools/`
- ❌ `caseGenerators/` → ✅ `case_generators/`

---

## 六、禁止的目录

以下目录结构被禁止：

| 禁止目录 | 原因 | 替代方案 |
|---------|------|---------|
| `config/` | 与 configs/ 重复 | 使用 configs/ |
| `tools/case_generators/` | 与 tools/ 重复 | 使用 tools/ |
| `tools/runners/` | 与 tools/ 重复 | 使用 tools/ |
| `modules/assets/` | 与 assets/ 重复 | 使用 assets/ |
| `tools/test_helpers/` | 非标准测试位置 | 删除或移至 tests/ |

---

## 七、文件清理规则

### 7.1 临时脚本

以下类型的文件应删除或移动到临时目录：

- 一次性使用的脚本
- 包含 "temp"、"demo"、"test" 的脚本（除非是正式测试）
- 根目录下的临时 Python 文件

### 7.2 冗余文件

以下类型的文件应删除：

- 重复的配置文件
- 未使用的模板
- 过时的文档

---

## 八、文档要求

### 8.1 必须的文档

- `README.md` - 项目说明
- `docs/ARCHITECTURE.md` - 架构设计
- `docs/PROJECT_STRUCTURE.md` - 项目结构（本文件）
- `docs/WORKFLOW.md` - 工作流程

### 8.2 文档命名

- 使用英文或中文
- 使用 PascalCase 或 snake_case
- 避免中英混用

---

## 九、架构原则

1. **模块化**: 每个模块有明确的职责边界
2. **扁平化**: 避免过深的目录嵌套
3. **一致性**: 统一的命名和结构规范
4. **最小化**: 删除冗余，保持简洁
5. **可追溯**: 清晰的文档和注释

---

*最后更新: 2026/6/10*
