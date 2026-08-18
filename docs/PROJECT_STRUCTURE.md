# 项目结构说明

> 版本：v2.1 · 2026-08-18
>
> 目录归属、文件生命周期、Git、清理和审核规则以
> [PROJECT_ARTIFACT_PLACEMENT.md](PROJECT_ARTIFACT_PLACEMENT.md) 为准；本文只描述当前代码结构，不与行为规范重复定义规则。

## 一、顶层结构

```text
test_erp/
├── .github/                         # CI/CD 工作流
├── assets/                          # 本地知识库和固定资源
│   └── knowledge_base/              # 本地业务知识库，不提交真实内容
├── configs/                         # 项目配置和脱敏配置模板
├── data/                            # 测试数据；data/private 为本地真实数据
├── docs/                            # 项目文档和专项规范
├── evaluation/                      # RAG 和质量评估代码/样例
├── fixtures/                        # 固定测试资源
│   ├── harness_plugin.py            # pytest 公共插件
│   └── templates/                   # 测试用例模板
├── modules/                         # 核心源码模块
│   ├── trae_test/                   # 测试用例生成和知识检索
│   └── auto_test/                   # 自动化测试执行
├── tests/                           # 通用、跨模块和单元测试
├── tools/                           # CLI、审核和维护工具
├── workspace/                       # 最终交付文件，按 YYYYMMDD 分目录
├── .runtime/                        # 缓存、日志、报告和临时产物
├── .venv/                           # 本地 Python 虚拟环境
└── browsers/                        # 浏览器运行环境
```

## 二、trae_test 模块

```text
modules/trae_test/
├── core/                            # 迁移和核心能力
├── orchestrator/                    # Agent 编排、审核和工作流
└── utils/
    ├── excel_generator.py           # 统一 Excel 生成器
    ├── file_splitter.py             # 知识文件分块
    ├── index_builder_v3.py          # 知识库索引构建
    ├── knowledge_retriever.py       # KnowledgeRetriever API
    ├── path_utils.py                # 项目和知识库路径工具
    ├── rag_generation.py            # RAG 生成能力
    ├── rag_semantic.py              # RAG 语义能力
    ├── runtime_paths.py             # runtime_dir() 统一运行时路径 API
    ├── template_builder.py          # 测试用例模板维护
    ├── test_case_generator.py       # 15 字段测试用例生成
    ├── test_case_strategy.py        # 评分、优化和重生策略
    └── workspace_manager.py         # workspace/YYYYMMDD/路径管理
```

## 三、auto_test 模块

```text
modules/auto_test/
├── api/                             # API 封装
├── configs/                         # 模块测试常量和本地配置
├── core/                            # 环境、数据、认证和运行时能力
├── drivers/                         # HTTP 和浏览器驱动
├── facades/                         # 业务操作封装
├── pages/                           # UI 页面对象
└── tests/                           # 模块专属回归测试
```

模块专属测试允许放在 `modules/auto_test/tests/`；通用或跨模块测试放在根目录 `tests/`。

## 四、工具目录

`tools/` 保持扁平，主要工具包括：

| 工具 | 用途 |
|---|---|
| `case_generator_cli.py` | 测试用例生成 CLI |
| `project_structure_auditor.py` | 项目结构和产物审核 |
| `clean_runtime.py` | 清理过期 `.runtime` 产物 |
| `kb_manager.py` | 知识库管理 |
| `report_generator.py` | 测试报告生成 |
| `verify_knowledge_base.py` | 知识库完整性验证 |

项目不提供自动清理 `workspace/` 历史测试用例的工具。

## 五、配置文件

正式配置位于 `configs/`，当前常用文件包括：

```text
configs/
├── audit_rules.yaml
├── database.yaml
├── redis.yaml
├── self_healing.yaml
├── strategy_config.yaml
├── test.yaml
├── uat.yaml
├── env_config.example.json
└── env_config.example.yaml
```

含真实凭据的本地配置不提交；脱敏模板使用 `.example` 命名。

## 六、命名和清理说明

- Python 文件使用 snake_case。
- 最终测试用例使用 `workspace/YYYYMMDD/`，文件名应包含需求或业务用途。
- 固定测试模板使用 `fixtures/templates/`，模板文件名由测试用例生成规范统一定义。
- 一次性脚本放 `.runtime/scripts/`，不因包含 `temp`、`demo` 或 `test` 就自动删除正式测试代码。
- `.runtime/` 中的报告、缓存、日志、截图和下载文件由 `clean_runtime.py` 管理。
- `workspace/` 历史测试用例是重要知识资产，由用户自行管理，禁止自动清理。
