---
title: 本地知识库使用指南
purpose: 本地知识库目录、隐私边界和维护入口
version: 3.0.0
updated: 2026-08-18
authority: 专项规范
---

# 本地知识库使用指南

本项目的真实知识库用于个人测试用例生成、回归自动化测试、CI 分片问题复盘等场景。默认应保留在本地，不建议上传到 GitHub。

## 目录约定

真实知识库存放在：

```text
assets/knowledge_base/
```

核心子目录：

```text
assets/knowledge_base/data/original/   原始知识文件
assets/knowledge_base/data/chunks/     自动分块文件
assets/knowledge_base/index/           检索索引
assets/knowledge_base/metadata/        文件注册表
```

`assets/knowledge_base/` 当前被 `.gitignore` 忽略，这是合理的：知识库中可能包含业务规则、测试数据、页面字段、订单号、SKU、环境信息和问题复盘，不适合公开提交。

## 推荐更新流程

新增知识：

```bash
python tools/kb_manager.py lint --file path/to/source.json
python tools/kb_manager.py migrate --source path/to/source.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword
```

更新已有知识：

```bash
python tools/kb_manager.py lint --file assets/knowledge_base/data/original/file_title.json
python tools/kb_manager.py process --file assets/knowledge_base/data/original/file_title.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword
```

## 推荐知识格式

```json
{
  "title": "auto_test_xxx_knowledge",
  "version": "1.0.0",
  "updated_at": "2026-07-24",
  "tags": ["自动化测试", "回归测试", "模块名"],
  "business_rules": [
    {
      "rule_id": "stable-rule-id",
      "module": "模块名",
      "keywords": ["关键词1", "关键词2"],
      "content": "可直接复用的经验、规则、断言边界或避坑说明",
      "status": "active",
      "version": "1.0.0",
      "owner": "业务负责人",
      "reviewed_at": "2026-09-16",
      "change_reason": "新增或修订原因"
    }
  ],
  "test_design_checklist": []
}
```

尽量使用扁平结构，避免过深嵌套。检索优先命中 `title`、`tags`、`business_rules[].keywords` 和 `business_rules[].content`。

新增 JSON 通过 `migrate` 时会严格校验：每条 `business_rules` 条目必须有文档内唯一的非空 `rule_id`、至少一个非空 `keywords` 和非空 `content`。导入后应对每个已声明关键词执行 `validate --keyword <词> --expect-rule-id <规则ID> --strict-rules`；`--keyword` 与 `--expect-rule-id` 都可以重复传入。既有知识默认保持兼容，只有明确传入 `--strict-rules` 时才要求补齐该契约。

## 规则生命周期

规则级生命周期字段均为可选；旧规则缺少 `status` 时按 `legacy`（历史兼容）处理，继续可检索，不能据此推断它当前有效。新规则建议明确填写以下字段：

- `status`：只能是 `draft`（草稿）、`active`（当前生效）、`deprecated`（已弃用但保留追溯）或 `superseded`（已被其他规则替代）。`superseded` 必须填写 `supersedes`。
- `version`：规则自身版本号，由维护者定义，不能由检索器自动递增。
- `supersedes`：被本规则替代的稳定 `rule_id` 列表。自引用会被拒绝；目标位于其他文件时只报告“需人工确认”的跨文件警告。
- `owner`、`reviewed_at`、`change_reason`：负责人、最近复核时间和变更原因，用于审计，不参与默认检索过滤。

默认 `search_business_rules()` 返回 `active`、`legacy`、`unknown` 和低优先级的 `deprecated`；默认排除 `draft` 和 `superseded`。通过 `include_history=True` 查看被替代历史，通过 `include_draft=True` 查看草稿。显式未知状态不会默认为 `active`，而标记为 `unknown` 并保持兼容返回。

状态切换、重复规则合并、删除和废弃判断都需要业务负责人或知识库管理员人工复核；系统只做契约校验和只读报告，不自动迁移状态、删除或合并规则。

## 周期健康门禁

可使用 `python tools/kb_health_check.py --include-dedupe --write-report` 执行只读健康门禁。退出码 `0` 为健康，`1` 为需要人工复核的警告，`2` 为阻断性失败。启用报告写入后，机器可读报告进入 `.runtime/reports/knowledge_base/`；不会写入知识库、`workspace/` 或索引。项目不自动创建系统级调度任务，频率、账号、通知和保留期由维护者配置。

## 隐私边界

知识写入前应避免包含：

- 密码、token、cookie、session
- 数据库连接串、内网地址、VPN 信息
- 真实客户姓名、电话、邮箱、地址
- 生产环境账号
- 完整真实订单或敏感业务数据

需要记录业务现象时，优先使用脱敏样例，例如 `SO2026xxxx`、`test_order_xxx`、`SKU-EXAMPLE-001`。
