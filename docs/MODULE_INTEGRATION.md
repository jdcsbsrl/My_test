# 模块间协作接口文档

## 概述

本文档描述 `trae_test` 和 `auto_test` 两个模块之间的协作机制和接口规范。

## 模块协作架构

```
┌─────────────────┐              ┌─────────────────┐
│   trae_test     │              │   auto_test     │
│  测试用例生成   │              │   自动化执行    │
└────────┬────────┘              └────────┬────────┘
         │                                │
         │  测试用例输出                   │
         ├───────────────────────────────►┤
         │                                │
         │  执行结果反馈                   │
         │◄───────────────────────────────┤
         │                                │
         ▼                                ▼
┌─────────────────────────────────────────────────┐
│          共享知识库 (assets/knowledge_base/)   │
└─────────────────────────────────────────────────┘
```

## 接口规范

### 1. 测试用例输出接口

**方向**: trae_test → auto_test

**数据格式**: JSON

**结构定义**:

```json
{
  "version": "1.0",
  "generated_at": "2026-05-05T10:00:00",
  "requirement_id": "REQ-001",
  "module": "sales",
  "cases": [
    {
      "case_id": "TC-SALES-001",
      "title": "测试销售订单创建",
      "priority": "P0",
      "preconditions": ["系统已登录", "存在可用商品"],
      "steps": [
        {"step": "1", "action": "进入销售订单页面"},
        {"step": "2", "action": "点击新建按钮"}
      ],
      "expected_results": ["订单创建成功", "返回订单详情页"],
      "test_type": "功能测试",
      "environment": "test"
    }
  ]
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| version | string | 数据格式版本 |
| generated_at | string | 生成时间 |
| requirement_id | string | 关联需求ID |
| module | string | 所属模块 |
| cases | array | 测试用例数组 |
| cases[].case_id | string | 用例唯一标识 |
| cases[].title | string | 用例标题 |
| cases[].priority | string | 优先级(P0/P1/P2) |
| cases[].preconditions | array | 前置条件列表 |
| cases[].steps | array | 测试步骤 |
| cases[].expected_results | array | 预期结果 |
| cases[].test_type | string | 测试类型 |
| cases[].environment | string | 测试环境 |

### 2. 执行结果反馈接口

**方向**: auto_test → trae_test

**数据格式**: JSON

**结构定义**:

```json
{
  "version": "1.0",
  "execution_id": "EXEC-20260505-001",
  "started_at": "2026-05-05T10:00:00",
  "completed_at": "2026-05-05T10:15:00",
  "requirement_id": "REQ-001",
  "results": [
    {
      "case_id": "TC-SALES-001",
      "status": "PASS",
      "actual_result": "订单创建成功",
      "execution_time": 1234,
      "screenshot": null
    },
    {
      "case_id": "TC-SALES-002",
      "status": "FAIL",
      "actual_result": "订单创建失败：商品库存不足",
      "execution_time": 892,
      "screenshot": "screenshots/fail_TC-SALES-002.png"
    }
  ],
  "summary": {
    "total": 10,
    "passed": 8,
    "failed": 2,
    "skipped": 0,
    "pass_rate": 80.0
  }
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| version | string | 数据格式版本 |
| execution_id | string | 执行ID |
| started_at | string | 开始时间 |
| completed_at | string | 完成时间 |
| requirement_id | string | 关联需求ID |
| results | array | 执行结果数组 |
| results[].case_id | string | 用例ID |
| results[].status | string | 状态(PASS/FAIL/SKIP) |
| results[].actual_result | string | 实际结果 |
| results[].execution_time | number | 执行耗时(ms) |
| results[].screenshot | string | 失败截图路径 |
| summary.total | number | 总用例数 |
| summary.passed | number | 通过数 |
| summary.failed | number | 失败数 |
| summary.skipped | number | 跳过数 |
| summary.pass_rate | number | 通过率(%) |

## 数据流转流程

```
用户需求
    │
    ▼
trae_test: 解析需求
    │
    ▼
trae_test: 检索知识库
    │
    ▼
trae_test: 生成测试用例
    │
    │ 输出测试用例(JSON)
    ▼
auto_test: 接收测试用例
    │
    ▼
auto_test: 执行测试
    │
    ▼
auto_test: 收集结果
    │
    │ 反馈执行结果(JSON)
    ▼
trae_test: 记录结果
    │
    ▼
生成测试报告
```

## 协作流程

### 流程1：测试用例生成与执行

1. **trae_test** 根据用户需求生成测试用例
2. **trae_test** 将测试用例导出为 JSON 格式
3. **auto_test** 读取测试用例文件
4. **auto_test** 执行测试并收集结果
5. **auto_test** 将执行结果反馈给 **trae_test**

### 流程2：测试结果分析与迭代

1. **trae_test** 接收执行结果
2. **trae_test** 分析失败用例
3. **trae_test** 根据失败原因优化测试用例
4. 重复执行流程1

## 接口调用示例

### Python 代码示例

```python
# trae_test 导出测试用例
from modules.trae_test.utils.test_case_generator import TestCaseGenerator

generator = TestCaseGenerator()
cases = generator.generate_cases(requirement_text)
generator.export_to_json(cases, 'workspace/20260727/test_cases.json')

# auto_test 执行测试
from modules.auto_test.api.api_client import ApiClient
import json

with open('workspace/20260727/test_cases.json', 'r') as f:
    test_cases = json.load(f)

client = ApiClient('test')
results = client.run_tests(test_cases)

# 保存执行结果
with open('workspace/20260727/test_results.json', 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# trae_test 导入执行结果
generator.import_results('workspace/20260727/test_results.json')
```

## 错误处理机制

### 数据格式错误

- **检测**: 验证 JSON 结构和必填字段
- **处理**: 抛出异常并记录错误日志

### 网络通信错误

- **检测**: 捕获连接超时、请求失败等异常
- **处理**: 重试机制、记录错误日志、通知用户

### 数据不完整

- **检测**: 验证关键字段是否存在
- **处理**: 使用默认值、标记缺失数据、提示补充

## 版本兼容性

| 接口版本 | 支持的模块版本 | 说明 |
|----------|---------------|------|
| 1.0 | trae_test v1.0+, auto_test v1.0+ | 初始版本 |

## 安全考虑

1. **环境隔离**: 测试仅在 test/uat 环境执行，禁止生产环境
2. **数据加密**: 敏感配置信息使用环境变量
3. **访问控制**: 基于模块的知识库访问权限限制
