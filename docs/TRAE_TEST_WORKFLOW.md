---
title: trae_test 模块工作流程
purpose: 需求生成、自动校验、固定字段和用例版本管理
version: 4.1.0
updated: 2026-11-12
authority: 专项规范
---

# trae_test 模块工作流程

## 日常入口

使用 `tools/case_generator_cli.py generate`，提供模块、功能及 `--requirement` 或 `--requirement-file`。
本地AI助手通过 `--candidate-file` 提交依据检索结果起草的15字段JSON对象，或由多个对象组成的数组；数组中的每条都是独立场景，仍逐条经过固定字段处理，并作为整组交给AuditAgent审核，全部通过后统一导出。传入的审核通过标记不会被信任。
知识库没有覆盖新需求时，可用 `--user-evidence` 或 `--user-evidence-file` 附上用户明确的业务依据。该来源以内容摘要单独标识，不伪装为知识库命中、不自动形成有限规则契约；未定义的业务语义仍须标记并核对。
`--provider self-hosted-llm` 使用已配置的内网模型，并按需求和知识中有依据、可独立验证的场景返回用例数组；若依据确实只支持一个场景，才返回一条，不为凑数量拆分或编造场景。旧模型返回单个对象时仍兼容为一条。`local-rule`仅保留为评估基线；正式生成入口在没有候选时明确返回生成能力缺口，不再输出通用步骤。
模型端点必须符合现有环境和隐私约束。生成器不会把知识发送到公共服务。

```text
需求正文 → KnowledgeRetriever（可补充用户依据）→ 一个或多个场景候选 → 程序逐条填入固定字段并评分 → 整组AuditAgent审核与发布门禁 → 统一Excel交付
```

固定字段来自 `RuleManager.get_field_value_rules()`。单一合法值或配置 `fixed: true` 的字段由程序锁定；
`fixed: true` 使用 `default_value`，模型没有修改权。其他枚举字段仍按原有合法值校验，
不能因为字段有默认值就擅自把它变成固定值。缺失值按现有默认配置填充。

## 质量与确认规则

质量评分是结构参考分，不代表业务正确性、覆盖率或执行稳定性。85仅为结构提示线，不作为交付门槛。
原始评分、优化后评分和最终评分通过 `_runtime_quality`、`score_history` 保留。
执行次数和冷启动信息仅作运行历史上下文；新用例没有执行历史，不因此触发人工确认或阻断导出。
正式Excel仍严格保持15列，唯一表头定义为 `template_builder.ALL_FIELDS`。

TestCaseOptimizer 仅整理已有编号和换行，不补通用句子，不增加预期结果，不截断用例标题。
没有新信息时不反复重生，不通过提高优先级或增加文字凑分。

AuditAgent 检查字段、固定值、业务对象、步骤、可观察预期和关联依据。
依据存在不等于系统已经证明全部业务语义；当前规则审核不能替代对未知规则的澄清。
缺少依据、内容冲突或关键信息不足时，生成诊断保留在 `.runtime/reports/`，汇总问题一次返回。
已明确的固定值和业务知识不重复询问。检索异常必须报告，禁止转换为默认通用用例。
检索无结果时返回 `missing_knowledge`；业务依据缺口返回 `needs_information`；通过返回 `ready`。
模型产生的字段、格式或不可执行内容错误返回 `generation_failed` 并记录诊断，不包装成让用户批准固定字段的问题。

格式和业务审核通过即可交付；结构参考分低于85不单独阻断。未解决的业务问题仍阻断。
正式“用例状态”保持原配置，内部审核和生命周期状态不得覆盖此字段。

## 测试用例质量与运行时契约

测试用例必须通过知识库 API 生成，使用统一 15 字段模板和 Excel 生成器；标准15字段中删除“关联缺陷ID”，第15列为“质量评分”。前置条件、执行步骤、预期结果必须基于业务知识和页面对象分点描述，便于测试人员直接操作；用例还必须登记功能点、业务规则、页面对象和覆盖矩阵。经过质量评分、优化和审核后，最终 `.xlsx` 文件写入 `workspace/YYYYMMDD/`：格式审核、固定字段校验和业务内容审核通过才允许导出；质量评分仅作结构参考。中间 JSON、评分轨迹、审核报告和临时 Excel 写入 `.runtime/`。原始评分、优化后评分、最终评分及冷启动信息只保留在运行时和审核报告中，不扩展正式Excel表头。回归执行按变更风险选择冒烟、模块、影响域或全量范围，核心 P0 用例不得因缩减回归而跳过。重生次数以 `TestCaseRegenerationLoop` 配置为准，保留兼容上限3次；当前格式整理仅执行一次，无新增依据不反复凑分。

### 测试用例质量门禁契约

- 前置条件至少 2 个分点，必须说明账号/权限、页面入口、业务数据或业务状态中的适用项。
- 执行步骤至少 3 个分点；每步必须包含明确页面对象、动作和必要测试数据，禁止使用“进入相关页面”等空泛表述。
- 预期结果至少 2 个分点；必须对应步骤并描述可观察、可验证的页面、提示、数据或状态变化，禁止仅写“成功”或“符合预期”。
- AuditAgent 必须同时检查格式、结构、业务可执行性、业务规则与页面对象一致性、覆盖矩阵和回归标识。
- 业务依据缺失、关键歧义或矛盾未解决时，必须阻断审核和导出；新用例没有执行历史，不因此触发人工确认。结构参考分缺失或非法时修复字段，低于85不单独阻断。
- 适量回归按变更风险执行：冒烟回归覆盖核心主流程；模块回归覆盖受影响模块及关联异常；影响域回归覆盖公共能力的依赖方；发布或核心重构执行全量回归。P0 用例必须执行。

### 运行时评分与覆盖矩阵字段契约

运行时字段必须使用 `_runtime_` 命名空间，不能增加或改写正式15列Excel表头。评分状态统一写入 `_runtime_quality`，版本写入 `_runtime_quality_version`；其字段为：`original_score`、`optimized_score`、`final_score`、`score_history`、`score_threshold`、`is_cold_start`、`confidence`、`optimization_attempts`、`needs_human_review`、`final_audit_passed`。结构参考分提示线保留85分，`score_history`必须保留原始评分和每次优化评分，冷启动信息只能作为运行历史上下文，不构成交付门槛。

覆盖矩阵统一写入 `_runtime_coverage_matrix`，版本写入 `_runtime_coverage_matrix_version`；矩阵维度为业务规则、业务对象、正常场景、异常场景、边界场景、回滚场景和排除项。矩阵缺口、回归范围和审核结果写入 `.runtime/reports/`，不得写入正式Excel。正式Excel仍严格保持15列，表头必须严格等于 `template_builder.ALL_FIELDS`。

活动用例登记表位于 `data/private/case_registry.sqlite3`，记录稳定ID、版本、停用原因、脚本关联及执行证据。该文件是持久业务资产，不属于临时缓存，不自动清理。固定字段由 RuleManager 配置控制，默认值不自动等同固定值。

有限业务契约映射使用`_runtime_rule_binding`保存来源ID、规则ID、版本、场景及程序核对的规则摘要/判断。
映射随用例版本进入登记内容JSON，参与版本指纹，不扩展Excel十五列，也不回写业务知识库。

### 测试用例命名
**格式**: 需求{id}{需求名}.xlsx
- **{id}**: 需求ID（可选），如果有则包含
- **{需求名}**: 需求名称（必填）

**示例**:
- 需求1001236销售订单SKU图片显示.xlsx（有需求ID）
- 需求销售订单导出时间优化.xlsx（无需求ID）

**禁止**:
- 禁止使用旧的命名格式（如：`测试用例_<模块>_<日期>.xlsx`）
- 最终交付文件禁止使用.json、.md等其他格式
- 禁止文件名包含特殊字符（\ / : * ? " < > |）
- 禁止文件名过长（建议不超过100字符）

### 测试用例交付格式
**必须**: 最终测试用例交付文件使用.xlsx格式
**禁止**: 最终测试用例交付文件使用.json、.md、.csv格式；中间产物按产物管理规范保存
**模板**: 必须使用统一的15字段标准模板（fixtures/templates/测试用例模板.xlsx）

### Excel内容规范
**必须包含**:
- 标准15字段表头（顺序必须正确）
- 用例内容与标题相符
- 数据完整性（无空行、无乱码）

**15字段标准顺序**:
1. 用例目录
2. 用例名称
3. 需求ID
4. 前置条件
5. 用例步骤
6. 预期结果
7. 用例类型
8. 用例状态
9. 用例等级
10. 创建人
11. 优先级
12. 是否可自动化
13. 回归测试标识
14. 知识库关联
15. 质量评分


评分审核统一以格式整理流程写入的“最终评分”为结构参考分值，并同步回写“质量评分”；两者不一致时审核阻断，避免重复计算造成导出前分数漂移。

## 交付与历史

Excel 使用既有 ExcelGenerator 和固定模板，写入 `workspace/YYYYMMDD/`，历史交付不自动删除。
生成诊断、来源摘要、审核结果写入 `.runtime/reports/`；`_runtime_coverage_matrix` 不增加正式列。

使用 `--register` 时必须给出稳定需求ID。登记表存于被Git忽略的 `data/private/case_registry.sqlite3`，
不放入可清理的缓存目录。相同内容复用已有ID；同名不同内容提示更新，不直接激活重复用例。
`update` 必须指定原用例ID、诊断文件、索引及变更原因，并重新审核。旧版本保留。
`retire` 仅停用活动版本，不删除历史。当前相似识别只处理精确内容及同名候选，不能声称语义去重。

```bash
python tools/case_generator_cli.py generate --module 销售 --function 订单查询 --requirement-file data/private/requirement.txt --requirement-id REQ-DEMO --provider self-hosted-llm --register
python tools/case_generator_cli.py list-cases --requirement-id REQ-DEMO
python tools/case_generator_cli.py list-cases --history
```

## 自动化关联

用例登记表中的 `script_id` 关联模块内具体pytest节点。`update --script-id` 可写入关联。
`tools/run_regression.py` 默认只预览：`--case-id <ID>` 显示活动版本与脚本，`--scope <范围>` 显示场景计划；两者都必须显式加 `--execute` 才执行。
同一需求的活动P0用例不能被选择范围遗漏。执行结果关联执行时的ID和版本，保留证据位置。
登记用例执行会校验授权、环境和 `script_id`，并由 pytest 执行绑定节点、生成执行证据；`--scope` 则通过独立的只读查询路径执行。两条路径都不会自动将自然语言用例编译成测试脚本。

## 日常维护和本地助手工作方式

用户提供需求和业务知识，本地助手负责检索、起草候选、调用生成入口；不要求用户手写候选JSON或逐字段确认。
规则审核只能验证已实现的契约，业务语义仍由起草和审核时核对依据，不能声称程序证明了所有业务正确性。

```bash
python tools/case_generator_cli.py generate --module 销售 --function 订单查询 --requirement-file data/private/requirement.txt --requirement-id REQ-DEMO --candidate-file .runtime/reports/candidate.json --register
python tools/case_generator_cli.py health --requirement-id REQ-DEMO --stale-days 30
```

`health`列出未执行、最近未通过、超过指定天数未执行、脚本未关联/节点失效/内容变化，以及同需求内正文高度相似的候选。
相似度是文字比较，不是语义判定；它不会自动合并或停用用例。停用仍使用`retire --reason`，所有历史保留。
脚本关联版本保存内容指纹；脚本变化后必须审核并使用`update --script-id --reason`建立新版本。
旧登记表自动新增指纹表，不覆盖历史；没有指纹的旧关联在health中提示补充，使用update补齐。

## 有限规则契约与变化选择

检索API结果可携带`content.query_contracts`，每条契约定义`id`、`revision`、`object`、`scenario`、`assertions`和`expected_text`。
这些契约应由业务依据整理并核对后维护；候选模型输出不能充当来源契约。未结构化的旧知识仍可使用，但不能宣称业务语义已验证。
候选通过`_runtime_rule_binding`关联`source_id`、`rule_id`、`revision`和`scenario`；来源必须存在于本次检索结果。
该字段只属于运行时元数据，不增加正式Excel列。审核通过后程序记录规则内容摘要及判断，登记表随用例版本持久保留。

首批判断支持`eq`（订单号/状态相等）、`contains`（关键字匹配）、`count_range`（记录数范围）、`disjoint`（两页订单号不重叠）；空结果只有在契约明确允许时才可通过。
预期文本必须与来源契约的核对文本一致；不做通用自然语言等价判断，改写也可能被要求修正。
`semantic_status=contract_checked`表示匹配已核对契约，不代表步骤、任意语义或真实产品已被全面证明；没有契约时标记`unverified`。
来源契约本身的正确性仍需要基于业务知识核对，程序无法证明未经核对的源规则。

```text
python tools/case_generator_cli.py impact --requirement-id REQ-DEMO --query 完整需求规则关键词
```

该命令通过KnowledgeRetriever读取当前规则，对比已登记的内容摘要，输出变化/缺失原因和建议回归ID，并补入同需求P0。
需要检索完整相关规则；检索不到不能解释成未变化，会保守标记缺失。无映射旧用例列入unverified_case_ids，需单独核对。
变化预览不执行测试、不自动更新版本、不停用或删除用例。update重新检索审核；新规则版本不继承旧版本的PASS。
相似候选先按已有来源、规则、场景分组，无映射旧用例保留文字相似提示。
