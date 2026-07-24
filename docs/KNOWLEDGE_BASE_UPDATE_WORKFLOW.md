# 知识库更新工作流程规范

> 本项目真实知识库默认保留在本地：`assets/knowledge_base/`。原始知识文件位于
> `assets/knowledge_base/data/original/`，不要使用早期非 `data/` 分层目录。如需提交到 GitHub，应只提交工具代码、流程文档和脱敏样例，
> 不提交真实业务知识内容。详细约定见 `docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md`。

## 📚 概述

本规范定义了test_erp项目中知识库更新的标准化工作流程，确保所有Agent在更新知识库时都遵循统一的操作步骤，保证知识库的完整性和可检索性。

## 🎯 核心原则

1. **自动化优先**: 所有更新操作应通过知识库管理系统进行，而非直接操作文件
2. **完整性保障**: 更新后必须验证文件完整性
3. **索引同步**: 更新后必须重建索引
4. **版本追踪**: 保留原始文件备份

## 🔄 标准工作流程

### 阶段一：准备阶段

**1.1 检查文件状态**
```bash
# 检查文件是否存在
python tools/kb_manager.py list

# 检查特定文件信息
python tools/kb_manager.py verify --title "销售模块"
```

**1.2 备份原始文件（自动）**
- 系统自动将原始文件备份到 `assets/knowledge_base/data/original/`
- 保留历史版本记录

### 阶段二：执行阶段

**2.1 更新内容**

**方式A: 使用 kb_manager.py（推荐）**
```bash
# 更新已存在的文件（自动分割+重建索引）
python tools/kb_manager.py process --file "assets/knowledge_base/data/original/销售模块.json"

# 强制更新（覆盖现有块）
python tools/kb_manager.py process --file "assets/knowledge_base/data/original/销售模块.json" --force
```

**方式B: 使用API**
```python
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

retriever = KnowledgeRetriever()

# 更新文件（自动处理分割和索引）
result = retriever.update_file("assets/knowledge_base/data/original/销售模块.json")

# 检查结果
if result.get("success"):
    print("更新成功！")
else:
    print(f"更新失败: {result.get('error')}")
```

**方式C: 添加新文件**
```bash
# 迁移新文件到知识库
python tools/kb_manager.py migrate --source "path/to/new_file.json"

# 使用API添加
result = retriever.add_file("path/to/new_file.json")
```

**2.2 批量更新**
```bash
# 处理所有超过阈值的文件
python tools/kb_manager.py process-all

# 扫描知识库并更新索引
python tools/kb_manager.py scan
```

### 阶段三：验证阶段

**3.1 验证完整性**
```bash
# 验证单个文件
python tools/kb_manager.py verify --title "销售模块"

# 验证所有文件
python tools/verify_knowledge_base.py
```

**3.2 验证检索功能**
```bash
# 运行演示脚本验证
python tools/demo_retriever.py

# 或使用API验证
result = retriever.retrieve("销售")
if result:
    print("检索功能正常！")
```

**3.3 检查索引状态**
```bash
# 列出所有可用索引
python tools/kb_manager.py list-indexes
```

### 阶段四：完成阶段

**4.1 记录更新日志**
- 系统自动记录更新时间、操作人、变更内容
- 更新日志存储在索引文件中

**4.2 通知相关系统**
- 如果配置了回调函数，自动通知相关系统
- 触发索引更新通知

## 🔧 工具使用指南

### kb_manager.py 命令参考

| 命令 | 语法 | 功能说明 |
|------|------|---------|
| **list** | `python kb_manager.py list` | 列出所有知识库文件 |
| **process** | `python kb_manager.py process --file <path>` | 完整处理文件（分割+索引） |
| **split** | `python kb_manager.py split --file <path>` | 仅分割文件 |
| **index** | `python kb_manager.py index --file <path>` | 仅重建索引 |
| **verify** | `python kb_manager.py verify --title <title>` | 验证文件完整性 |
| **migrate** | `python kb_manager.py migrate --source <path>` | 迁移新文件 |
| **process-all** | `python kb_manager.py process-all` | 批量处理所有文件 |
| **scan** | `python kb_manager.py scan` | 扫描知识库 |

### API 接口参考

```python
class KnowledgeRetriever:
    def update_file(file_path, auto_process=True):
        """更新现有文件，自动处理分割和索引"""
    
    def add_file(file_path, auto_process=True):
        """添加新文件到知识库"""
    
    def retrieve(keyword, mode="auto"):
        """智能检索知识库内容"""
    
    def load_aggregated_data(file_title):
        """加载完整的聚合数据"""
    
    def clear_caches():
        """清除缓存（更新后调用）"""
```

## 📊 索引重建流程

### 索引类型

| 索引类型 | 路径 | 说明 |
|---------|------|------|
| **全局索引** | `index/knowledge_base_index.json` | 所有文件的元数据 |
| **文件索引** | `index/<title>_index.json` | 单个文件的块级索引 |
| **块级索引** | 块文件内置 | 每个块的特征信息 |

### 重建时机

| 场景 | 是否需要重建索引 | 命令 |
|------|----------------|------|
| 文件内容更新 | ✅ 是 | `kb_manager.py index` |
| 文件大小变化 | ✅ 是 | `kb_manager.py process` |
| 新文件添加 | ✅ 自动 | `kb_manager.py migrate` |
| 块文件变更 | ✅ 自动 | `kb_manager.py process` |

## 🚨 异常处理

### 常见问题及解决方案

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| **文件被占用** | 另一个程序正在使用 | 关闭其他程序，重新执行 |
| **哈希不匹配** | 格式变化（紧凑→格式化） | 正常现象，不影响使用 |
| **索引过时** | 未重建索引 | 运行 `kb_manager.py index` |
| **分割失败** | 文件格式错误 | 检查JSON格式是否正确 |
| **检索失败** | 缓存未更新 | 调用 `retriever.clear_caches()` |

### 故障排除流程

```
更新失败 → 检查错误信息 → 手动执行步骤 → 验证结果
    ↓
错误信息分析:
    - 文件被占用 → 关闭其他程序
    - JSON错误 → 修复文件格式
    - 索引错误 → 手动重建索引
    - 其他错误 → 查看详细日志
```

## 📝 最佳实践

### 1. 自动化集成
在Agent代码中集成知识库更新API，避免直接操作文件：

```python
def update_knowledge_base(title, content):
    """标准化的知识库更新函数"""
    from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
    
    # 保存到临时文件
    temp_path = f"temp_{title}.json"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    
    # 使用管理系统更新
    retriever = KnowledgeRetriever()
    result = retriever.update_file(temp_path)
    
    # 清理临时文件
    os.remove(temp_path)
    
    # 验证结果
    if result.get("success"):
        print(f"✅ 知识库'{title}'更新成功")
        return True
    else:
        print(f"❌ 知识库'{title}'更新失败: {result.get('error')}")
        return False
```

### 2. 定期维护
```bash
# 每天执行一次维护
python tools/kb_manager.py process-all
python tools/verify_knowledge_base.py
```

### 3. 版本控制
- 将原始文件提交到版本控制系统
- 定期备份索引文件
- 保留更新历史记录

## 📋 检查清单

### 更新前检查
- [ ] 文件是否已关闭
- [ ] 是否有足够的磁盘空间
- [ ] 是否需要备份当前版本

### 更新中检查
- [ ] 是否使用了正确的命令/API
- [ ] 是否添加了 `--force` 参数（如需覆盖）
- [ ] 是否监控了处理进度

### 更新后检查
- [ ] 文件是否成功分割
- [ ] 索引是否重建成功
- [ ] 完整性验证是否通过
- [ ] 检索功能是否正常

## 🎯 预期成果

遵循本规范后，知识库更新将实现：

1. ✅ **自动化**: 无需手动分割和索引
2. ✅ **完整性**: 保证数据不丢失
3. ✅ **可检索性**: 索引始终最新
4. ✅ **可追踪性**: 完整的更新日志
5. ✅ **可靠性**: 验证机制确保质量

---

**文档版本**: v1.0  
**创建日期**: 2026-05-12  
**适用范围**: test_erp项目所有知识库更新操作  
**维护责任**: 自动化测试团队
