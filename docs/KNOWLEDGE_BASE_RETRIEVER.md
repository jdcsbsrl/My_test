# 知识库智能检索系统使用指南

## 📚 概述

知识库智能检索系统是test_erp项目的核心组件，用于管理、组织和检索业务知识库文件。该系统支持文件分割、索引构建和智能检索，有效解决了大文件超出上下文窗口的问题。

## 🎯 核心功能

### 1. 智能检索
支持按模块、关键词、业务规则等多种方式检索知识库内容。

```python
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

# 创建检索器实例
retriever = KnowledgeRetriever()

# 自动模式检索（推荐）
result = retriever.retrieve("销售")  # 检索销售模块

# 指定模式检索
result = retriever.retrieve("订单", mode="rules")  # 检索业务规则
result = retriever.retrieve("日志", mode="requirements")  # 检索需求清单
```

### 2. 分块管理
自动将大文件分割成小块，避免上下文溢出：

| 原始文件 | 大小 | 分割后块数 | 单块大小 |
|---------|------|-----------|---------|
| 销售模块.json | 218 KB | 3个块 | ≤80KB |
| 需求清单.json | 517 KB | 2个块 | ≤80KB |
| 已学习测试用例详情.json | 236 KB | 2个块 | ≤80KB |

### 3. 索引系统
构建多层次索引，支持快速定位：

- **文件级元数据**：标题、大小、创建日期、分类
- **块级特征**：关键词、摘要、位置
- **交叉引用**：相关内容的关联关系

## 🛠️ 使用工具

### kb_manager.py - 知识库管理CLI

```bash
# 列出所有知识库文件
python tools/kb_manager.py list

# 分割单个文件
python tools/kb_manager.py split --file path/to/file.json

# 为文件构建索引
python tools/kb_manager.py index --file path/to/file.json

# 完整处理文件（分割+索引）
python tools/kb_manager.py process --file path/to/file.json

# 验证文件完整性
python tools/kb_manager.py verify --title "销售模块"

# 批量处理所有大文件
python tools/kb_manager.py process-all

# 扫描知识库
python tools/kb_manager.py scan
```

### verify_knowledge_base.py - 完整性验证

```bash
# 验证知识库完整性
python tools/verify_knowledge_base.py

# 验证特定文件
python tools/kb_manager.py verify --title "销售模块"
```

### demo_retriever.py - 功能演示

```bash
# 运行演示脚本
python tools/demo_retriever.py
```

## 📁 目录结构

```
assets/knowledge_base/
├── original/                    # 原始文件备份
│   ├── 销售模块.json
│   ├── 需求清单.json
│   └── ...
├── content/                    # 分割后的块文件
│   ├── 销售模块_chunk_*.json
│   ├── 需求清单_chunk_*.json
│   └── ...
└── index/                      # 索引文件
    ├── knowledge_base_index.json
    └── *_index.json
```

## 🔧 API参考

### KnowledgeRetriever类

#### retrieve(keyword, mode="auto")
智能检索接口

**参数**：
- `keyword` (str): 搜索关键词
- `mode` (str): 检索模式
  - `"auto"`: 自动选择最佳检索方式（默认）
  - `"module"`: 按模块检索
  - `"rules"`: 检索业务规则
  - `"requirements"`: 检索需求清单

**返回值**：根据mode返回不同类型的数据

#### search_module(module_name)
按模块名称检索业务规则

**示例**：
```python
result = retriever.search_module("销售")
```

#### search_business_rules(keyword)
按关键词检索业务规则

**示例**：
```python
rules = retriever.search_business_rules("订单状态")
```

#### search_requirements(keyword="", module="")
检索需求清单

**示例**：
```python
requirements = retriever.search_requirements(keyword="日志", module="ERP销售订单模块")
```

#### get_all_chunks(file_title)
获取文件的所有内容块

**示例**：
```python
chunks = retriever.get_all_chunks("销售模块")
```

#### load_aggregated_data(file_title)
加载文件的完整聚合数据（优先使用块文件，回退到原始文件）

**示例**：
```python
data = retriever.load_aggregated_data("销售模块")
```

## ⚙️ 配置

### 阈值配置

默认文件大小阈值：**80KB**

在 `modules/trae_test/utils/kb_monitor.py` 中修改：

```python
DEFAULT_THRESHOLD_KB = 80
```

### 目录配置

在 `KnowledgeRetriever` 类中定义：

```python
KNOWLEDGE_BASE_DIR = "assets/knowledge_base"
INDEX_DIR = "assets/knowledge_base/index"
CONTENT_DIR = "assets/knowledge_base/content"
ORIGINAL_DIR = "assets/knowledge_base/original"
```

## 📊 最佳实践

### 1. 使用自动模式
大多数情况下使用 `retrieve(keyword)` 自动模式即可，系统会自动选择最佳检索策略。

### 2. 定期验证完整性
添加新文件后，运行验证工具确保数据完整：

```bash
python tools/kb_manager.py verify --title "新文件"
```

### 3. 使用索引加速检索
系统会优先使用索引进行快速检索，确保索引文件最新：

```bash
python tools/kb_manager.py scan
```

### 4. 处理大文件
超过80KB的文件会自动分割，无需手动处理。分割后的块会自动聚合返回完整内容。

## ❓ 常见问题

### Q: 为什么分割后哈希值不匹配？
A: 分割后的块使用格式化JSON（有缩进），而原始文件使用紧凑格式。这是正常的，不影响内容完整性。

### Q: 如何添加新文件到知识库？
A: 使用 `add_file` 方法或 `migrate` 命令：

```python
retriever.add_file("path/to/new_file.json")
```

### Q: 如何更新已分割的文件？
A: 重新分割并构建索引：

```bash
python tools/kb_manager.py split --file path/to/file.json --force
```

## 📝 版本历史

- **v1.0.0** (2026-05-11): 初始版本
  - 支持文件分割
  - 支持索引构建
  - 支持智能检索
  - 支持完整性验证
