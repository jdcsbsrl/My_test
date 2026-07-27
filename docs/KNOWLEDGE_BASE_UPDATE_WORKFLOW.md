# 知识库更新工作流程规范

> 本项目真实知识库默认保留在本地：`assets/knowledge_base/`。原始知识文件位于
> `assets/knowledge_base/data/original/`。如需提交到 GitHub，只提交工具代码、流程文档和脱敏样例，
> 不提交真实业务知识内容。详细约定见 `docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md`。

## 概述

本规范定义 test_erp 项目中知识库更新的标准流程。Agent 更新知识库时必须通过 `tools/kb_manager.py` 和 `KnowledgeRetriever` API，不直接读写原始业务 JSON。

## 核心原则

1. **隐私优先**: 导入前先 lint，避免写入密码、token、订单号、SKU、账号、环境地址等敏感内容。
2. **工具入口**: 新增、更新、扫描和验证都通过 `kb_manager.py` 完成。
3. **索引同步**: 更新后必须执行 `scan`，确保注册表、全局索引和倒排索引最新。
4. **检索验证**: 交付前必须执行 `validate`，确认知识能被检索命中。

## 新增知识流程

```bash
python tools/kb_manager.py lint --file path/to/source.json
python tools/kb_manager.py migrate --source path/to/source.json
python tools/kb_manager.py scan
python tools/kb_manager.py validate --title file_title --keyword keyword
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
| `scan` | 扫描知识库并刷新注册表/索引 |
| `validate --title <title> --keyword <keyword>` | 验证标题、索引和检索命中 |
| `list` | 列出知识库文件 |
| `verify --title <title>` | 验证文件完整性 |
| `process-all` | 批量处理知识库文件 |

## 检查清单

更新前：

- [ ] 源文件已脱敏
- [ ] 已执行 `lint`
- [ ] 标题和关键词可用于后续验证

更新后：

- [ ] 已执行 `migrate` 或 `process`
- [ ] 已执行 `scan`
- [ ] 已执行 `validate`
- [ ] 检索结果能命中新内容

---

**文档版本**: v3.2.0  
**最近更新**: 2026-07-27  
**适用范围**: test_erp 项目本地知识库更新操作
