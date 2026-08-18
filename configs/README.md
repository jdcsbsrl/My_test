# 运行环境配置说明

| 配置文件 | 用途 | 与 UAT 关系 |
|-----------|------|----------------|
| [test.yaml](test.yaml) | 默认自动化（`pytest --env=test`） | 可通过 `TEST_WEB_*` 覆盖基址；字段与 UAT 同构便于对齐用例 |
| [test_env.yaml](test_env.yaml) | 专用测试栈（`pytest --env=test_env`） | 推荐为测试环境独立主机/API；未设 `TEST_WEB_*` 时默认与 UAT 同址，仅用于占位联调 |
| [uat.yaml](uat.yaml) | UAT（`pytest --env=uat`） | 验收环境 |

## 数据隔离与功能一致性

- **功能一致性**：三套 YAML 中 `api.*`、`playwright.*` 等键对齐，差异主要在 `base_url` / `api_base_url` 与数据库连接。
- **数据隔离**：由 **不同主机、不同数据库、不同租户** 保证；本仓库只管理 URL 与连接串占位，不存放业务数据。
- **访问验证**：在本地配置 `.env`（参考仓库根目录 `.env.example`）后执行：

```bash
python tools/verify_test_env.py --env test_env
```

将检查网页基址可达性，并报告登录相关环境变量是否已配置（不打印秘密）。

## Customer OpenAPI 本地凭证（可选）

- 单账户：复制 [customer_openapi.local.example.env](customer_openapi.local.example.env) 为 `customer_openapi.local.env`（已 gitignore），填写 `OPENAPI_APP_KEY` / `OPENAPI_APP_SECRET`。
- 多账户：复制 [customer_openapi.accounts.example.json](customer_openapi.accounts.example.json) 为 `customer_openapi.accounts.local.json`（`configs/*.json` 默认忽略，勿提交）。
- 执行：`python tools/customer_openapi_field_compare.py`，报告写入 `.runtime/reports/`（已 gitignore）。
