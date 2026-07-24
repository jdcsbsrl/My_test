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
      "content": "可直接复用的经验、规则、断言边界或避坑说明"
    }
  ],
  "test_design_checklist": []
}
```

尽量使用扁平结构，避免过深嵌套。检索优先命中 `title`、`tags`、`business_rules[].keywords` 和 `business_rules[].content`。

## 隐私边界

知识写入前应避免包含：

- 密码、token、cookie、session
- 数据库连接串、内网地址、VPN 信息
- 真实客户姓名、电话、邮箱、地址
- 生产环境账号
- 完整真实订单或敏感业务数据

需要记录业务现象时，优先使用脱敏样例，例如 `SO2026xxxx`、`test_order_xxx`、`SKU-EXAMPLE-001`。
