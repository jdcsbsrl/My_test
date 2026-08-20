---
title: 项目文件与产物管理行为规范
purpose: 项目目录、运行时产物、workspace、Git 和清理边界
version: 2.1.0
updated: 2026-08-18
authority: 项目强制规范
---

# 项目文件与产物管理行为规范 v2.1

## 1. 适用范围

本规范约束开发人员、AI Agent、测试脚本、构建脚本和 CI/CD 产生的文件。核心原则是：长期维护内容进入正式目录，运行时产物进入 `.runtime/`，最终交付文件进入 `workspace/YYYYMMDD/`，真实敏感数据只保留本地。

## 2. 顶层目录总表

允许的项目目录：

```text
.github/ assets/ configs/ data/ docs/ evaluation/ fixtures/
modules/ tests/ tools/ workspace/ .runtime/ .venv/ browsers/
```

目录职责以第三章为准；本表是总表，不替代目录详细定义。

## 3. 目录职责

| 目录 | 职责 |
|---|---|
| `.github/` | CI/CD 工作流 |
| `assets/` | 本地知识库和固定资源；真实知识库不提交 |
| `configs/` | 正式配置和脱敏配置模板 |
| `data/` | 可变测试数据；真实数据放 `data/private/` |
| `docs/` | 项目规范和技术文档 |
| `evaluation/` | RAG 和质量评估代码/样例 |
| `fixtures/` | 固定、不可变测试资源 |
| `modules/` | 项目核心源码 |
| `tests/` | 通用和跨模块测试 |
| `tools/` | 通用工具和 CLI 脚本 |
| `workspace/` | 最终交付文件，按日期分目录 |
| `.runtime/` | 缓存、日志、报告和临时产物 |
| `.venv/` | 本地 Python 虚拟环境，不提交 |
| `browsers/` | 浏览器运行环境，不提交 |

## 4. workspace 规则

最终测试用例和用户交付文件直接放入 `workspace/YYYYMMDD/`，不创建 `formal/`、`draft/`、`test_cases/`、`exports/` 或模块子目录。`workspace/` 默认不进入 Git，只保留 `workspace/.gitkeep` 骨架；真实成果默认本地保存。workspace 是重要的历史测试知识库，任何自动清理工具都不得删除其中的历史文件；`workspace/.keep` 仅用于记录保护规则，不改变永久保留策略。

## 5. .runtime 规则

`.runtime/` 整体加入 `.gitignore`，只保留 `.keep` 或目录骨架。合法一级目录固定为：

```text
cache downloads logs reports scripts sheet_build uploads
```

`reports/` 可按需创建 `screenshots/`、`videos/`、`traces/`、`allure-results/`、`harness_metrics/`、`self_healing/`、`sales_report_regression/` 等子目录，均属于报告产物。`.runtime/.keep` 和子目录 `.keep` 中的匹配项由清理工具跳过。CI 只检查忽略规则和异常提交，本地使用 `tools/clean_runtime.py --keep-days 14` 清理。

## 6. 统一运行时 API

使用 [modules/trae_test/utils/runtime_paths.py](../modules/trae_test/utils/runtime_paths.py) 的 `runtime_dir()`。允许值固定为 `cache`、`downloads`、`logs`、`reports`、`scripts`、`sheet_build`、`uploads`。该 API 已实现项目根目录自动定位、绝对路径拒绝、`..` 拒绝、越界检查和自动建目录，并有单元测试。新增代码不得使用裸相对路径写文件；旧代码迁移期间由审核器先警告，迁移完成后再阻断。

## 7. 源码、脚本和测试

长期源码放 `modules/`，通用工具放 `tools/`，一次性脚本放 `.runtime/scripts/`。通用测试放 `tests/unit/`、`tests/integration/`、`tests/e2e/`；模块专属回归测试允许放在 `modules/<module>/tests/`，跟随模块维护。`evaluation/` 只保存评估代码和样例，评估结果写 `.runtime/reports/evaluation/`。

## 8. fixtures 与 data

固定、不可变、被代码直接引用的样本和模板放 `fixtures/`；可变、按环境或场景切换的输入放 `data/`。`data/test_accounts/` 只允许脱敏样例。真实数据统一放 `data/private/`，该目录被 Git 忽略，不提交。

## 9. 敏感数据

账号、Token、Cookie、订单号、SKU、客户信息、内网地址、真实业务规则和真实测试结果均为敏感数据。真实内容只保留本地，提交内容必须脱敏。`.env`、`data/private/`、`assets/knowledge_base/`、`.runtime/`、`workspace/`、`.venv/`、`browsers/` 默认不提交。

## 10. 根目录例外登记

工具强制要求的根文件可以例外保留，但必须登记在本文件的“根目录例外登记表”中，并填写文件名、所属工具、保留原因、是否被 CI 使用、是否可迁移。本表由 `project_structure_auditor.py` 解析；修改列结构必须同步更新审核器和单元测试。

| 文件 | 所属工具 | 保留原因 | CI 使用 | 可迁移 |
|---|---|---|---|---|
| `pyproject.toml` | Python | 构建和依赖配置 | 是 | 否 |
| `pytest.ini` | pytest | 测试配置 | 是 | 否 |
| `.env.example` | dotenv | 脱敏环境变量模板 | 否 | 否 |

## 11. 命名规则

长期文件使用 `{模块}_{用途}.{扩展名}`；运行时文件使用 `{用途}_{日期}_{uuid}.{扩展名}`。禁止 `new.xlsx`、`test2.json`、`最终版.xlsx` 等无语义名称。文件名不得包含 `\ / : * ? " < > |`。

## 12. 测试用例专项规则

测试用例必须通过知识库 API 生成，使用统一 15 字段模板和 Excel 生成器；标准15字段中删除“关联缺陷ID”，第15列为“质量评分”。前置条件、执行步骤、预期结果必须基于业务知识和页面对象分点描述，便于测试人员直接操作；用例还必须登记功能点、业务规则、页面对象和覆盖矩阵。经过质量评分、优化和审核后，最终 `.xlsx` 文件写入 `workspace/YYYYMMDD/`：格式审核、业务内容审核和最终评分均通过且最终评分 >= 85 才允许导出。中间 JSON、评分轨迹、审核报告和临时 Excel 写入 `.runtime/`。原始评分、优化后评分、最终评分及冷启动信息只保留在运行时和审核报告中，不扩展正式Excel表头。回归执行按变更风险选择冒烟、模块、影响域或全量范围，核心 P0 用例不得因缩减回归而跳过。重生次数以 `TestCaseRegenerationLoop` 配置为准，当前默认 3 次，必须具备冷却期和熔断机制。

### 测试用例质量门禁契约

- 前置条件至少 2 个分点，必须说明账号/权限、页面入口、业务数据或业务状态中的适用项。
- 执行步骤至少 3 个分点；每步必须包含明确页面对象、动作和必要测试数据，禁止使用“进入相关页面”等空泛表述。
- 预期结果至少 2 个分点；必须对应步骤并描述可观察、可验证的页面、提示、数据或状态变化，禁止仅写“成功”或“符合预期”。
- AuditAgent 必须同时检查格式、结构、业务可执行性、业务规则与页面对象一致性、覆盖矩阵和回归标识。
- 最终评分低于 85、评分缺失、冷启动评分未经业务复核或状态为 `needs_human_review` 时，必须阻断审核和导出。
- 适量回归按变更风险执行：冒烟回归覆盖核心主流程；模块回归覆盖受影响模块及关联异常；影响域回归覆盖公共能力的依赖方；发布或核心重构执行全量回归。P0 用例必须执行。

### 运行时评分与覆盖矩阵字段契约

运行时字段必须使用 `_runtime_` 命名空间，不能增加或改写正式15列Excel表头。评分状态统一写入 `_runtime_quality`，版本写入 `_runtime_quality_version`；其字段为：`original_score`、`optimized_score`、`final_score`、`score_history`、`score_threshold`、`is_cold_start`、`confidence`、`optimization_attempts`、`needs_human_review`、`final_audit_passed`。评分门槛固定为85分，`score_history`必须保留原始评分和每次优化评分，冷启动信息只能作为审核上下文，不能单独放行交付。

覆盖矩阵统一写入 `_runtime_coverage_matrix`，版本写入 `_runtime_coverage_matrix_version`；矩阵维度为业务规则、业务对象、正常场景、异常场景、边界场景、回滚场景和排除项。矩阵缺口、回归范围和审核结果写入 `.runtime/reports/`，不得写入正式Excel。正式Excel仍严格保持15列，表头必须严格等于 `template_builder.ALL_FIELDS`。

## 13. 审核与 CI

`project_structure_auditor.py` 检查目录、输出位置、workspace 禁止子目录、根目录脚本和异常产物。`--json` 模式将机器可读 JSON 输出到 stdout。退出码为：0 通过，1 警告，2 阻断。CI 在 push 和 pull request 时执行；pre-commit 可配置：

本地 pre-commit 对任何非零退出码都会阻断提交，这是有意的：本地提交应先处理警告；CI 则按退出码区分警告和阻断。

```yaml
- repo: local
  hooks:
    - id: project-structure-audit
      name: project structure audit
      entry: python tools/project_structure_auditor.py --json
      language: system
      pass_filenames: false
```

## 14. 清理规则

`tools/clean_runtime.py --keep-days 14` 清理过期运行时文件；正式清理前可使用 `--dry-run` 预览待删除文件。项目不提供自动清理 `workspace/` 的工具；workspace 历史测试用例由用户自行管理。运行时清理工具跳过 `.keep` 中匹配的文件，不处理 `assets/knowledge_base/`、`data/private/` 和 `workspace/`。评分审核统一以优化流程写入的“最终评分”为唯一权威分值，并同步回写“质量评分”；两者不一致时审核阻断，避免重复计算造成导出前分数漂移。

## 15. 变更记录

| 版本 | 变更 |
|---|---|
| v1.0 | 初始目录和产物规范 |
| v2.0 | 增加 workspace、`.runtime`、运行时 API、审核退出码 |
| v2.1 | 补齐实际目录、模块测试、私有数据、`.keep`、CI、例外登记和清理规则 |
