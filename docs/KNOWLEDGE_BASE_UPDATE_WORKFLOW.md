---
title: 知识库更新工作流程规范
purpose: 知识库 lint、迁移、处理、扫描和验证
version: 3.0.0
updated: 2026-08-18
authority: 专项规范
---

# 知识库更新工作流程规范

> 本项目真实知识库默认保留在本地：`assets/knowledge_base/`。原始知识文件位于
> `assets/knowledge_base/data/original/`。如需提交到 GitHub，只提交工具代码、流程文档和脱敏样例，
> 不提交真实业务知识内容。详细约定见 `docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md`。

## 概述

本规范定义 test_erp 项目中知识库更新的标准流程。Agent 更新知识库时必须通过 `tools/kb_manager.py` 和 `KnowledgeRetriever` API，不直接读写原始业务 JSON。

## 核心原则

1. **隐私优先**: 导入前先 lint，避免写入密码、token、订单号、SKU、账号、环境地址等敏感内容。
2. **工具入口**: 新增、更新、扫描和验证都通过 `kb_manager.py` 完成。
3. **索引同步**: 更新后必须执行 `scan` 检查状态；需要全量重建时必须显式调用索引构建流程，不能把状态扫描当作重建。
4. **检索验证**: 交付前必须执行 `validate`，确认知识能被检索命中。

## 新增知识流程

```bash
python tools/kb_manager.py lint --file path/to/source.json
python tools/kb_manager.py migrate --source path/to/source.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword --expect-rule-id stable-rule-id --strict-rules
```

## 更新已有知识流程

```bash
python tools/kb_manager.py lint --file assets/knowledge_base/data/original/file_title.json
python tools/kb_manager.py process --file assets/knowledge_base/data/original/file_title.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword
```

## 检索使用方式

Agent 访问知识库时必须使用 `KnowledgeRetriever`：

```python
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

r = KnowledgeRetriever()
result = r.retrieve("销售订单")

if not result:
    result = r.search_business_rules("销售订单")
```

当 registry 缺失、疑似过期或出现 `FileNotFoundError` 时，先执行：

```python
r.refresh_registry()
```

## 目录结构

```text
assets/knowledge_base/
├── data/original/    # 原始知识文件
├── data/chunks/      # 大文件自动分块
├── index/global/     # 全局索引
├── index/inverted/   # 倒排索引
└── metadata/         # 文件注册表
```

## 命令参考

| 命令 | 用途 |
|------|------|
| `lint --file <path>` | 检查知识源格式和敏感内容 |
| `migrate --source <path>` | 将新知识源迁移到本地知识库 |
| `process --file <path>` | 处理已有知识文件，必要时分块并重建索引 |
| `scan` | 只读扫描知识库状态，报告待处理、缺失和不一致文件 |
| `health --json` | 只读检查注册表/全局索引一致性及处理状态，不修改知识或索引 |
| `dedupe --json` | 只读报告规范化标题、跨文件规则 ID、规则正文指纹重复及相似候选；不删除或合并知识 |
| `python tools/kb_health_check.py [--include-dedupe] [--write-report]` | 周期健康门禁；只读输出 JSON，退出码 0/1/2 分别表示健康/警告/阻断 |
| `validate --title <title> --keyword <keyword>` | 验证标题、索引和检索命中 |
| `list` | 列出知识库文件 |
| `verify --title <title>` | 验证文件完整性 |
| `process-all` | 批量处理知识库文件 |

`dedupe` 的标题和正文重复判定仅忽略 Unicode 形式、大小写和空白差异；相似候选使用字符二元组 Jaccard 分数，只供人工复核，不能证明两条业务规则等价。所有清理、合并、停用或改写仍必须取得明确授权并保留审计记录。

## 检查清单

更新前：

- [ ] 源文件已脱敏
- [ ] 已执行 `lint`
- [ ] 标题和关键词可用于后续验证
- [ ] 新增 JSON 的每条 `business_rules` 规则均具有唯一 `rule_id`、非空 `keywords` 和非空 `content`

更新后：

- [ ] 已执行 `migrate` 或 `process`
- [ ] 已执行 `scan`
- [ ] 已执行 `validate`
- [ ] 检索结果能命中新内容
- [ ] 使用每个声明的关键词和对应的 `--expect-rule-id` 验证目标规则

## 规则检索契约

`migrate` 会严格校验新增 JSON 的结构化规则：`business_rules` 必须为非空列表，且每条规则必须具有文档内唯一的非空 `rule_id`、至少一个非空 `keywords` 项和非空 `content`。这使导入后的规则可按稳定标识和业务词断言。

既有知识不会因普通 `process` 或普通 `validate` 被拒绝。维护旧 JSON 时，可显式使用 `--strict-rules` 先检查并补齐契约；新规则建议重复传入 `--keyword` 和 `--expect-rule-id` 完成检索验收。多个关键词都必须命中文件；期望规则 ID 必须出现在全部关键词检索结果的并集中。

## 生命周期字段与人工边界

`business_rules[]` 可以附加 `status`、`version`、`supersedes`、`owner`、`reviewed_at` 和 `change_reason`。`status` 仅允许 `draft`、`active`、`deprecated`、`superseded`；`superseded` 必须提供至少一个被替代的稳定 `rule_id`，且不得自引用。严格契约校验会阻断非法状态、缺失替代列表和自引用；非严格校验对历史文件保留兼容并给出警告。

`supersedes` 目标若在同一文件中可确定，校验会检查其存在；目标不在当前文件时不直接判错，而报告跨文件引用警告，必须由维护者确认目标是否真实存在。检索器不会自动变更状态，也不会因状态缺失删除旧规则：无 `status` 的旧规则标记为 `legacy`，显式未知值标记为 `unknown`。

`search_business_rules(keyword, include_history=False, include_draft=False)` 默认排除 `draft` 和 `superseded`，`deprecated` 仍可返回但排序靠后；显式 `include_history=True` 查看被替代历史，显式 `include_draft=True` 查看草稿。两个参数不会改变源文件或索引，扩展查询也不使用默认缓存结果，避免不同生命周期视图互相污染。

生命周期状态切换、替代关系确认、重复规则合并、删除和废弃均属于人工业务判断。健康检查、去重报告和契约验证只提供证据，不自动执行高风险清理。

## 周期健康门禁

可由外部调度器周期执行：

```bash
python tools/kb_health_check.py --include-dedupe --write-report
```

门禁始终只读，不写入知识源、注册表或索引。退出码约定为：`0` 表示无发现；`1` 表示有待处理文件或重复/相似候选，需要人工复核；`2` 表示健康检查、索引一致性、去重读取或报告写入失败。启用 `--write-report` 时，报告写入 `.runtime/reports/knowledge_base/`，不会触碰 `workspace/` 和 `assets/knowledge_base/`。

本项目只提供门禁脚本，不自动创建 Windows Task Scheduler、Cron 或 Codex Automation。调度频率、执行账号、通知策略和报告保留期必须由项目负责人明确配置；调度器应根据退出码处理告警和阻断。

---

**文档版本**: v3.2.0  
**最近更新**: 2026-07-27  
**适用范围**: test_erp 项目本地知识库更新操作
