---
title: 编码规范
purpose: Python、测试、命名、质量和安全编码规则
version: 2.1.0
updated: 2026-08-18
authority: 专项规范
---
# 编码规范

## Python 代码规范

### 命名规范

| 类型 | 规范 | 示例 |
|-----|------|-----|
| 类名 | CapWords | `class SalesOrderPage` |
| 函数名 | snake_case | `def get_order_list()` |
| 常量 | UPPER_SNAKE | `MAX_RETRY_COUNT = 3` |
| 变量 | snake_case | `order_id = 123` |
| 私有变量 | _prefix | `_auth_token` |
| pytest fixture | snake_case | `@pytest.fixture def auth_token()` |

### 导入规范
```python
# 标准库
import os
import json
from datetime import datetime

# 第三方库
import pytest
import requests
from loguru import logger

# 本地库（按相对路径从近到远）
from modules.auto_test.facades.api.sales_order_facade import SalesOrderFacade
from modules.auto_test.core.config_manager import Config
from modules.auto_test.pages.sales_order_page import SalesOrderPage
```

### 函数设计原则
```python
# ✅ 推荐：单一职责，参数清晰，有返回类型
def filter_orders_by_status(api: SalesOrderFacade, status: str, limit: int = 100) -> dict:
    """过滤指定状态的订单"""
    response = api.filter(status=status, limit=limit)
    return response.json()
```

## Pytest 测试规范

### 测试函数命名
```python
# ✅ 推荐：描述性命名
def test_api_filter_returns_correct_status(api_client):
    ...

def test_ui_tab_navigation_to_fba(page):
    ...
```

### 断言风格
```python
# ✅ 推荐：清晰的断言消息
assert response.status_code == 200, f"期望 200，实际 {response.status_code}"

# ✅ 多个相关断言
assert "data" in response.json(), "响应缺少 data 字段"
assert len(response.json()["data"]["list"]) > 0, "订单列表为空"
```

## 日志规范

### 日志级别使用
```python
logger.debug("调试信息：请求参数 {params}")  # 详细调试
logger.info("开始执行：查询客户 {customer_id}")  # 一般信息
logger.warning("重试中：第 {attempt} 次尝试")  # 警告
logger.error("请求失败：{error}", exc_info=True)  # 错误
```
