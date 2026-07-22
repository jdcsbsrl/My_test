# auto_test 模块工作流程

## 模块定位

`auto_test` 是自动化测试执行模块，负责配置测试环境、执行测试脚本、收集测试结果并生成可视化报告。

## 工作流程

### 流程架构

```
测试触发
     │
     ▼
┌─────────────────────┐
│ 环境配置阶段        │
│  验证环境           │
│  初始化数据工厂     │
│  注册生命周期回调   │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│ 测试数据准备阶段    │
│  加载测试数据       │
│  生成动态数据       │
│  执行 setUp 任务    │
└───────┬─────────────┘
        │
        ▼
┌───────────────┐
│ 测试执行阶段  │
│  运行脚本    │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ 结果收集阶段  │
│  收集日志    │
└───────┬───────┘
        │
        ▼
┌─────────────────────┐
│ 测试数据清理阶段    │
│  级联删除测试数据   │
│  DB 兜底清理        │
└───────┬─────────────┘
        │
        ▼
┌───────────────┐
│ 报告生成阶段  │
│  可视化输出  │
└───────────────┘
```

### 阶段详细说明

#### 阶段1：环境配置与验证

**输入**: 环境配置文件（test.yaml/uat.yaml）

**处理步骤**:
1. 读取环境配置文件
2. 验证环境类型（test/uat）
3. 检查环境安全性（禁止生产环境）
4. 验证API端点和认证信息
5. 初始化 TestDataFactory（注册数据生成器）
6. 初始化 TestDataLifecycleManager（注册 setUp/cleanup 回调）

**可访问知识库**:
- 自动化规范/*
- 测试规范/测试用例模板与优先级规则.json
- 业务规则/销售模块.json
- 业务规则/销售订单字段规范.json

**输出**: 环境验证报告

#### 阶段2：测试数据准备

**输入**: 测试数据文件 / 数据生成配置

**处理步骤**:
1. 使用 DataLoader 加载外部测试数据（JSON/YAML/CSV/Excel）
2. 使用 DynamicDataGenerator 生成动态数据（随机字符串/邮箱/手机号/关联数据）
3. 使用 DataVersionManager 管理数据版本（保存/回滚）
4. 执行 TestDataLifecycleManager.setup() 按拓扑序执行依赖任务

**关键工具**:
| 工具 | 用途 |
|------|------|
| DataLoader | 多格式文件加载，支持懒加载/流式模式避免OOM |
| DynamicDataGenerator | 带缓存的动态数据生成，支持依赖注入 |
| DataVersionManager | 测试数据文件版本控制 |
| TestDataLifecycleManager | 数据生命周期编排（拓扑排序执行setUp） |

**输出**: 就绪的测试数据

#### 阶段3：测试脚本执行

**输入**: 测试用例/测试脚本 + 准备就绪的测试数据

**处理步骤**:
1. 加载测试脚本
2. 初始化 Playwright 浏览器
3. 执行测试用例
4. 记录执行日志

**支持的测试类型**:
- UI自动化测试（Playwright）
- API接口测试
- 回归测试

**输出**: 测试执行日志

#### 阶段4：测试结果收集

**输入**: 测试执行日志

**处理步骤**:
1. 解析测试结果
2. 统计通过率/失败率
3. 收集失败截图和日志
4. 生成测试结果摘要

**输出**: 测试结果数据

#### 阶段5：测试数据清理

**输入**: 测试阶段创建的上下文数据

**处理步骤**:
1. 自动触发 TestDataLifecycleManager.execute_cleanup()
2. 按后创建先清理顺序执行 cleanup 任务
3. 如 API 清理失败，自动降级到 DB 直连兜底清理
4. 清理失败记录日志但不会阻塞整体流程

**关键配置**:
- 生产环境（production）禁用 DB 兜底，防止数据风险
- 非生产环境（test/staging）启用 DB 兜底作为容错

**输出**: 清理操作日志

#### 阶段6：报告生成与展示

**输入**: 测试结果数据

**处理步骤**:
1. 生成 HTML 可视化报告
2. 生成 JSON 格式报告（便于集成）
3. 发送测试结果通知

**输出**: 测试报告（HTML/JSON）

## 支持的测试环境

| 环境 | 配置文件 | 说明 |
|------|----------|------|
| test | configs/test.yaml | 内部测试环境 |
| uat | configs/uat.yaml | 用户验收测试环境 |

## 数据流转路径

```
测试配置 ──► 环境验证器 ──► 数据准备器 ──► 测试执行器 ──► 结果收集器 ──► 数据清理器 ──► 报告生成器
                │              │               │
                ▼              ▼               ▼
          TestDataFactory  DataLoader/    Playwright浏览器
          + Lifecycle     DynamicDataGen
              回调注册         + VersionMgr
```

## 关键操作步骤

### 启动自动化测试（含数据生命周期管理）

```python
from modules.auto_test.core.environment import Environment
from modules.auto_test.api.api_client import ApiClient
from modules.auto_test.core.test_data_factory import (
    DataLoader, DynamicDataGenerator, DataVersionManager, TestDataFactory
)
from modules.auto_test.core.test_data_lifecycle import TestDataLifecycleManager

# 1. 初始化环境
env = Environment('test')
env.validate()

# 2. 初始化数据工厂
factory = TestDataFactory()
loader = DataLoader()
data_gen = DynamicDataGenerator()
version_mgr = DataVersionManager(data_dir="test_data/versions")

# 3. 注册数据生命周期
lifecycle = TestDataLifecycleManager(env="test")

def create_order_setup():
    order_data = loader.load("test_data/orders.json")
    return data_gen.generate("related_order_no", cache_key="order_no")

lifecycle.register_setup_task(create_order_setup, task_name="create_order")
lifecycle.register_cleanup_task(
    lambda: print("Cleanup order"),
    fallback=lambda: print("DB fallback cleanup"),
)

# 4. 执行 setUp（拓扑排序自动处理依赖）
lifecycle.execute_setup()

# 5. 创建API客户端并执行测试
client = ApiClient(env)
results = client.run_tests(test_cases)

# 6. 执行 tearDown（自动级联清理 + DB兜底）
lifecycle.execute_cleanup()

# 7. 生成报告
from tools.report_generator import ReportGenerator
report = ReportGenerator()
report.generate(results, output_path)
```

### 执行流程

1. **初始化环境**: 创建 `Environment` 实例，指定环境类型
2. **验证环境**: 调用 `validate()` 验证环境配置 + 初始化数据工厂/生命周期
3. **准备测试数据**: 加载文件、生成动态数据、执行 setUp 任务（拓扑排序）
4. **创建客户端**: 使用环境配置创建 `ApiClient`
5. **执行测试**: 调用 `run_tests()` 执行测试用例
6. **清理测试数据**: 调用 `execute_cleanup()` 级联删除 + DB 兜底
7. **生成报告**: 使用 `ReportGenerator` 生成可视化报告

## 异常处理

| 异常场景 | 处理策略 |
|----------|----------|
| 环境配置错误 | 抛出异常并提示配置问题 |
| 测试脚本失败 | 记录失败日志和截图 |
| 网络超时 | 重试机制（最多3次） |
| 认证失败 | 提示检查凭证 |

## 输出格式规范

### HTML报告格式
- 文件名: `regression_report_<日期>_<时间>.html`
- 内容: 测试概览、详细结果、失败截图、统计图表

### JSON报告格式
- 文件名: `regression_report_<日期>_<时间>.json`
- 内容: 结构化测试结果数据

### 报告内容
- 测试执行时间
- 用例总数/通过数/失败数
- 通过率统计
- 失败用例详情
- 执行耗时分析