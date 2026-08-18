# Test ERP Agent Workspace Index

> 本文件是项目 Agent 的控制面和启动入口，不是项目手册。
> 它只定义任务路由、入口索引和不可绕过的红线；具体实践必须阅读对应专项规范。

## 1. 强制启动协议

每次开始项目操作前，必须确认项目根目录并读取本文件。未读取前，不得执行项目文件修改、删除、移动、测试、提交或推送操作。

执行顺序固定为：

```text
读取 AGENTS.md → 识别任务类型 → 读取专项规范 → 执行任务 → 测试与审核 → 检查 Git 变更 → 汇报影响
```

涉及新增、生成、移动、删除或整理项目文件和运行产物时，必须先读取 [项目文件与产物管理行为规范](docs/PROJECT_ARTIFACT_PLACEMENT.md)。

## 2. 规则优先级

```text
系统规则 / 平台安全规则
    > 用户当前明确要求
    > AGENTS.md
    > 专项规范
    > 代码与测试实现
    > 默认 Agent 行为
```

系统安全规则不可被项目文档覆盖。发生冲突时必须停止受影响的操作，向用户说明冲突和影响；用户明确要求与项目规范冲突时，按用户要求执行前必须说明风险和影响。

## 3. 核心红线

1. **环境红线**：自动化测试仅允许在 UAT/内网测试环境执行（项目配置标识：`test`、`uat`）。
2. **授权红线**：测试执行需用户明确批准；未经用户明确授权，不得擅自提交、推送、删除或覆盖用户已有改动。
3. **数据红线**：必须通过 `KnowledgeRetriever` API 访问知识库，禁止直接按文件路径读取原始JSON。
4. **目录红线**：临时缓存、日志、报告、下载文件和脚本进入 `.runtime/`；最终测试用例和交付文件进入 `workspace/YYYYMMDD/`。
5. **历史红线**：workspace 下的历史测试用例和交付记录永久保留，任何自动清理工具不得触碰。
6. **审核红线**：所有任务交付前必须经过适用的测试、结构审核和 AuditAgent 审核。
7. **保护红线**：执行前后必须核对 Git 状态，不得覆盖、回滚或删除用户未提交的改动。

## 4. 任务路由

| 任务类型 | 必读专项规范 | 代码/工具入口 | 验证入口 |
|---|---|---|---|
| 测试用例生成 | [TRAE_TEST_WORKFLOW.md](docs/TRAE_TEST_WORKFLOW.md) | `test_case_generator.py`、`case_generator_cli.py` | 测试用例测试与人工审核 |
| 自动化测试执行 | [AUTO_TEST_WORKFLOW.md](docs/AUTO_TEST_WORKFLOW.md) | `run_regression.py`、`auto_test/` | 目标测试与报告 |
| 知识库检索 | [KNOWLEDGE_BASE_RETRIEVER.md](docs/KNOWLEDGE_BASE_RETRIEVER.md) | `KnowledgeRetriever` | 检索 API 测试 |
| 知识库更新 | [KNOWLEDGE_BASE_UPDATE_WORKFLOW.md](docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md) | `tools/kb_manager.py` | lint / scan / validate |
| 文件与产物管理 | [PROJECT_ARTIFACT_PLACEMENT.md](docs/PROJECT_ARTIFACT_PLACEMENT.md) | `runtime_paths.py`、`clean_runtime.py` | 结构审计与产物测试 |
| 代码审核 | [AGENT_RULES.md](docs/AGENT_RULES.md)、[CODING_RULES.md](docs/CODING_RULES.md) | `AuditAgent` | `AuditResult` 与审核测试 |
| 文档维护 | 本文件、[PROJECT_ARTIFACT_PLACEMENT.md](docs/PROJECT_ARTIFACT_PLACEMENT.md) | `doc_consistency_checker.py` | 契约测试与文档一致性检查 |
| 环境配置 | [VIRTUAL_ENV.md](docs/VIRTUAL_ENV.md) | `configs/`、环境管理代码 | 配置检查与目标测试 |

## 5. 知识库访问索引

| 索引项 | 位置 | 用途 |
|---|---|---|
| 本地知识库使用指南 | [LOCAL_KNOWLEDGE_BASE_GUIDE.md](docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md) | 目录、隐私边界和格式 |
| 检索使用指南 | [KNOWLEDGE_BASE_RETRIEVER.md](docs/KNOWLEDGE_BASE_RETRIEVER.md) | API、上下文窗口和检索边界 |
| 更新工作流 | [KNOWLEDGE_BASE_UPDATE_WORKFLOW.md](docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md) | lint、迁移、处理和验证 |
| 管理工具 | [kb_manager.py](tools/kb_manager.py) | 知识库生命周期操作 |
| 检索 API | [knowledge_retriever.py](modules/trae_test/utils/knowledge_retriever.py) | Agent 唯一访问入口 |
| 索引构建器 | [index_builder_v3.py](modules/trae_test/utils/index_builder_v3.py) | 维护 v3 索引 |

**知识库 API 版本**: 3.0.0  
**架构**: HarnessEngineer  
**最近审查时间**: 2026-08-18

知识库文件数量以 registry/API 为准，关键词数量以索引元数据为准。业务文件列表必须动态获取，例如 `r.get_index()` 或 `r.list_available_files()`；不得在 Agent 指令中硬编码具体文件清单。

## 6. 任务与代码入口

### 测试用例生成

- [test_case_generator.py](modules/trae_test/utils/test_case_generator.py)：标准字段生成。
- [test_case_strategy.py](modules/trae_test/utils/test_case_strategy.py)：评分、优化和 `TestCaseRegenerationLoop`。
- [excel_generator.py](modules/trae_test/utils/excel_generator.py)：统一 Excel 生成。
- [case_generator_cli.py](tools/case_generator_cli.py)：命令行入口。

### 自动化测试与报告

- [AUTO_TEST_WORKFLOW.md](docs/AUTO_TEST_WORKFLOW.md)：执行流程和数据生命周期。
- [run_regression.py](tools/run_regression.py)：回归测试入口。
- [report_generator.py](tools/report_generator.py)：`TestReportGenerator`，使用 `--help` 查看参数。
- [runtime_paths.py](modules/trae_test/utils/runtime_paths.py)：统一运行时路径 API。

### 审核与编排

- [audit_agent_enhanced.py](modules/trae_test/orchestrator/audit_agent_enhanced.py)：`AuditAgent` 阻塞式审核入口。
- [audit_models.py](modules/trae_test/orchestrator/audit_models.py)：`AuditResult` / `AuditIssue` 结果契约。
- [multi_agent_runner.py](tools/multi_agent_runner.py)：多 Agent 协同编排入口。

## 7. 文件、产物与 workspace 索引

详细规则唯一来源为 [PROJECT_ARTIFACT_PLACEMENT.md](docs/PROJECT_ARTIFACT_PLACEMENT.md)。

- `.runtime/`：缓存、下载、日志、报告、脚本、上传和构建临时产物。
- `workspace/YYYYMMDD/`：最终测试用例和交付文件；历史内容不自动清理。
- `data/private/`：本地真实敏感数据；只保留脱敏样例或骨架文件。
- `assets/knowledge_base/`：本地业务知识库，默认不进入 Git。
- `fixtures/`：代码引用的不可变脱敏样本和模板。
- `data/`：可变、按场景切换的脱敏输入数据；真实数据放 `data/private/`。

运行时目录由 `runtime_dir()` 管理，允许的 kind 由 `RUNTIME_KINDS` 固定。`tools/clean_runtime.py` 只清理 `.runtime/`；项目不提供 workspace 自动清理工具。

## 8. 测试、审核与 CI

完成任务后按范围执行：

1. 目标功能测试；
2. `pytest tests/unit/test_agents_md_contract.py`；
3. `python tools/project_structure_auditor.py --json`；
4. `python tools/doc_consistency_checker.py --json`；
5. 必要时执行全量单元测试；
6. `git diff --check` 和 Git 状态对照。

审核结果复用 `AuditResult.to_dict()`，不创建平行结果格式。审核退出码统一为：`0` 通过、`1` 警告、`2` 阻断。独立 CI 结构审核 job 不依赖允许失败的代码质量 job。

本地 pre-commit 对任何非零退出码均阻断提交，这是预期行为；CI 对退出码 `1` 记录警告，对退出码 `2` 阻断合并。

## 9. Git 与交付

- 修改前保存 Git 状态快照，完成后与快照逐项对照。
- 只处理用户当前授权范围，不擅自扩大文件范围。
- AGENTS.md 与 `test_agents_md_contract.py` 的契约变更必须在同一修改批次完成，不允许产生不匹配的中间状态。
- 提交和推送必须获得用户明确授权。
- 最终汇报必须说明修改内容、功能影响、Agent 行为影响、目录/产物影响、测试结果、审核结果和未解决风险。

## 10. 项目索引

| 类别 | 入口 |
|---|---|
| 项目说明 | [README.md](README.md) |
| 架构设计 | [ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 项目结构 | [PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |
| 整体工作流 | [WORKFLOW.md](docs/WORKFLOW.md) |
| 审核规则 | [AGENT_RULES.md](docs/AGENT_RULES.md) |
| 文件与产物规则 | [PROJECT_ARTIFACT_PLACEMENT.md](docs/PROJECT_ARTIFACT_PLACEMENT.md) |
| 结构审核 | [project_structure_auditor.py](tools/project_structure_auditor.py) |
| 文档一致性审核 | [doc_consistency_checker.py](tools/doc_consistency_checker.py) |

## 11. 完整索引

- Agent 配置索引：Trae 专属配置已移除，通用规则见 [AGENT_RULES.md](docs/AGENT_RULES.md)。
- 知识库全局索引：`assets/knowledge_base/index/global/`。
- 逐文件索引：`assets/knowledge_base/index/files/`。
- 向量索引：`assets/knowledge_base/index/vector/`。
