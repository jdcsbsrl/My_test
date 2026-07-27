# 配置文件使用说明

## 概览

本项目统一使用 `configs/` 管理环境与凭证示例配置，测试数据位于 `data/yaml/`。历史 `config/` 目录口径已废弃，请勿新增或引用。

自动化测试只允许在授权的 TEST/UAT 环境执行，禁止连接生产环境。

## 目录结构

```text
test_erp/
├── configs/
│   ├── README.md
│   ├── env_config.example.json
│   ├── env_config.example.yaml
│   ├── test.yaml
│   ├── uat.yaml
│   ├── customer_openapi.accounts.example.json
│   └── customer_openapi.local.example.env
└── data/yaml/
    ├── auth_matrix.yaml
    ├── customer_api_test_data.yaml
    └── sales_order_filters.yaml
```

## 本地配置

1. 从 `configs/env_config.example.json` 或 `configs/env_config.example.yaml` 复制一份本地配置。
2. 填入授权测试环境的 URL、账号和必要参数。
3. 本地真实配置、认证状态、API 密钥等敏感文件不得提交到 Git。

禁止提交的常见文件包括：

```text
configs/env_config.json
configs/auth_state.json
configs/customer_openapi.accounts.local.json
configs/customer_openapi.local.env
```

只有 `.example.*` 示例文件可以提交。

## Customer OpenAPI 凭证

单账号模式：复制 `configs/customer_openapi.local.example.env` 为 `configs/customer_openapi.local.env`，填入 `OPENAPI_APP_KEY`、`OPENAPI_APP_SECRET` 和 `OPENAPI_BASE_URL`。

多账号模式：复制 `configs/customer_openapi.accounts.example.json` 为 `configs/customer_openapi.accounts.local.json`，按需补充账号信息。

## 测试数据

`data/yaml/` 下保存可提交的脱敏测试数据：

| 文件 | 用途 |
|------|------|
| `auth_matrix.yaml` | 权限矩阵配置 |
| `customer_api_test_data.yaml` | Customer API 测试数据 |
| `sales_order_filters.yaml` | 销售订单筛选条件测试数据 |

## 相关模块

- `modules/auto_test/core/environment.py`: 环境配置与白名单校验
- `modules/auto_test/core/config_manager.py`: 配置加载
- `modules/auto_test/core/login_service.py`: 登录与 token 管理
- `modules/auto_test/facades/auth_facade.py`: 认证业务封装

更多细节见 `configs/README.md`。
