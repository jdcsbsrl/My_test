# Test ERP 架构设计

> 版本 2.0.0 · 2026/7/16 · 基于 HarnessEngineer 规范

---

## 模块设计

### 1. modules/trae_test/ - 测试用例生成模块

**职责**: 负责测试用例的生成、管理、导出等功能

**核心组件**:
- `utils/test_case_generator.py`: 测试用例生成器（15 字段标准格式）
- `utils/knowledge_retriever.py`: 知识库检索工具（v3.0）
- `utils/template_builder.py`: 测试模板构建器
- `utils/test_case_strategy.py`: 测试用例策略引擎（评分/优化/重生闭环）
- `utils/file_splitter.py`: JSON文件分割器（语义分割）
- `utils/index_builder_v3.py`: 索引构建器（TF-IDF关键词）
- `orchestrator/audit_agent_enhanced.py`: 全能审核Agent

### 2. modules/auto_test/ - 自动化测试执行模块

**职责**: 负责测试脚本的执行、环境配置、结果收集

**核心组件**:
- `core/environment.py`: 环境配置管理
- `core/logger.py`: 日志管理
- `core/test_data_factory.py`: 测试数据工厂（加载/生成/版本管理）
- `core/test_data_lifecycle.py`: 测试数据生命周期管理（setUp/cleanup）
- `drivers/`: 浏览器和 HTTP 驱动
- `pages/`: UI 页面对象模型
- `api/`: API 接口封装
- `facades/`: 业务逻辑封装层
- `reporting/`: 测试报告生成

---

## 工作流程

```
需求分析 → 测试场景设计 → 测试用例生成 → 
测试脚本转换 → 测试执行 → 结果收集与分析 → 报告生成
```
