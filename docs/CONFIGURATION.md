# 配置文件使用说明

## 概述

⚠️ **重要安全限制：自动化测试只能在授权的测试域名上运行！**
- UAT: `your-uat-erp.example.com`
- TEST: `your-test-erp.example.com`

本项目包含两个测试模块的完整配置文件：
1. `trae_test` 模块（测试用例生成）配置位于 `config/`
2. `auto_test` 模块（自动化测试执行）配置位于 `configs/` 和 `data/yaml/`

## 配置文件目录结构

```
test_erp/
├── config/                     # trae_test 模块配置
│   ├── env_config.json         # 实际环境配置（敏感，不提交）
│   ├── env_config.example.json # 环境配置示例（可提交）
│   └── auth_state.json         # 认证状态（cookies和token，不提交）
│
├── configs/                    # auto_test 模块配置
│   ├── README.md               # 配置说明（可提交）
│   ├── customer_openapi.accounts.example.json # API账号示例（可提交）
│   └── customer_openapi.local.example.env # 环境变量示例（可提交）
│
└── data/yaml/                  # 测试数据（可提交）
    ├── auth_matrix.yaml        # 权限矩阵配置
    ├── customer_api_test_data.yaml # API测试数据
    └── sales_order_filters.yaml # 销售订单筛选条件
```

## trae_test 模块配置

### 1. 环境配置

`config/env_config.json` 包含以下内容：

```json
{
  "environments": {
    "UAT": {
      "base_url": "https://your-uat-erp.example.com/login",
      "description": "UAT测试环境",
      "allowed": true
    },
    "TEST": {
      "base_url": "https://your-test-erp.example.com/login",
      "description": "测试环境",
      "allowed": true
    }
  },
  "test_accounts": {
    "业务员": {
      "account": "test_sales_user",
      "password": "your_password_here",
      "description": "业务员账号，拥有销售订单、采购等业务权限"
    },
    "管理员": {
      "account": "test_admin_user",
      "password": "your_password_here",
      "description": "管理员账号，拥有系统管理权限"
    },
    "组长": {
      "account": "test_team_leader",
      "password": "your_password_here",
      "description": "组长账号，拥有业务组管理权限，员工下拉仅显示本组人员"
    }
  },
  "browser": {
    "headless": false,
    "slow_mo": 500,
    "viewport": {
      "width": 1920,
      "height": 1080
    }
  }
}
```

### 2. 认证状态

`config/auth_state.json` 保存浏览器登录后的 cookies 和 localStorage，避免重复登录。

### 3. 使用步骤

1. 从 `config/env_config.example.json` 复制为 `config/env_config.json`
2. 填入实际的测试环境 URL 和账号密码
3. 确认配置正确后即可使用

## auto_test 模块配置

### 1. 环境配置

`configs/` 目录包含自动化测试的配置文件，参考 `configs/README.md` 了解详细使用方法。

### 2. API 凭证

`customer_openapi.local.example.env` 是单账号 API 凭证示例：

```
OPENAPI_APP_KEY=ak_xxxxxxxx
OPENAPI_APP_SECRET=sk_xxxxxxxx
OPENAPI_BASE_URL=https://your-openapi.example.com
```

多账号凭证请参考 `customer_openapi.accounts.example.json`。

### 3. 使用步骤

1. 根据需要选择单账号或多账号配置方式
2. 从示例文件复制为实际配置文件（.local.env 或 .local.json）
3. 填入真实的 API 密钥

## 测试数据配置

### 1. 权限矩阵

`data/yaml/auth_matrix.yaml` 定义了不同角色的权限范围：

| 角色 | 数据范围 | 权限 |
|------|---------|------|
| 业务员 | 个人数据 | 查看、新增、编辑、删除 |
| 组长 | 组内数据 | 查看、新增、编辑、删除、审核 |
| 管理员 | 全部数据 | 全部权限 |

### 2. API 测试数据

`data/yaml/customer_api_test_data.yaml` 包含：
- API 端点定义
- 测试用例数据
- 预期响应结构

### 3. 筛选条件配置

`data/yaml/sales_order_filters.yaml` 包含销售订单高级筛选的所有条件配置，用于测试筛选功能。

## Git 提交安全规则

**重要：** 以下文件禁止提交到 Git：

```
config/env_config.json         # 实际环境配置（含密码）
config/auth_state.json         # 认证状态（含token）
configs/customer_openapi.accounts.local.json # API凭证
configs/customer_openapi.local.env # 环境变量
```

只有 `.example.*` 示例文件可以提交，确保团队成员可以看到配置结构，而不会泄露敏感信息。

## 登录测试使用指南

### 快速开始

1. 确保依赖已安装：
   ```bash
   pip install pyyaml requests python-dotenv
   ```

2. 运行登录测试：
   ```bash
   cd d:\Working\test_erp
   python tools\login_test.py
   ```

### 测试内容

该脚本会依次测试两个环境：
- TEST 环境：https://your-test-erp.example.com
- UAT 环境：https://your-uat-erp.example.com

### 使用的账号

默认使用管理员账号（从 .env 文件读取）：
- 用户名：${TEST_USERNAME}
- 密码：${TEST_PASSWORD}

### 核心模块介绍

- `core/login_service.py`：登录服务，负责获取和管理token
- `core/config_manager.py`：配置管理器，加载环境配置
- `core/environment.py`：环境验证，确保只在允许的环境运行
- `facades/auth_facade.py`：认证Facade，封装登录API调用

### 安全验证

每次执行前会自动验证环境是否在允许的白名单中，防止意外在生产环境运行。

## 常见问题

### Q: 配置文件丢失了怎么办？
A: 从 ".example.*" 文件复制一份，填入实际信息。

### Q: 为什么有两个配置目录 config/ 和 configs/？
A: "config/" 属于 trae_test 模块，"configs/" 属于 auto_test 模块，保持原有项目结构便于迁移。

### Q: 测试数据文件可以提交吗？
A: "data/yaml/" 目录下的测试数据可以提交，不包含敏感信息。

### Q: 如何在代码中使用登录功能？
A:
```python
from core.login_service import get_login_service

login_service = get_login_service()
result = login_service.login()

if result["success"]:
    token = result["token"]
    # 使用token进行后续操作
```

---

如有疑问，请查看 "configs/README.md" 或联系项目维护者。
