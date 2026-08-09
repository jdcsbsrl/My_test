# 自动化测试执行分层

第三阶段将 UI 回归分为三层，所有层级仅允许在测试/UAT 环境执行。

## 冒烟

验证登录、核心页面加载和最小导出链路：

```text
pytest -m smoke -p no:asyncio -p no:rerunfailures
```

## 核心回归

验证库存查询、销售商品销量报表和关键导出：

```text
pytest -m core -p no:asyncio -p no:rerunfailures
```

## 完整回归

运行所有单元、集成和 UI 用例。历史长流程按文件或用例单独执行，避免单个模板/导出流程掩盖其他结果。

```text
pytest tests/unit tests/integration -p no:asyncio
pytest modules/auto_test/tests -p no:asyncio -p no:rerunfailures
```

每次执行应保留 `reports/test-summary.json`、`reports/test-attempts.jsonl`、Allure 结果以及失败截图/Trace（若启用）。质量检查和诊断信息为 warning，不直接阻断流水线；业务数据写操作不属于本阶段范围。
