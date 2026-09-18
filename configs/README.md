# 运行环境配置说明

| 配置来源 | 用途 | 与 UAT 关系 |
|-----------|------|----------------|
| [test.yaml](test.yaml) | 默认自动化（`pytest --env=test`） | 可通过 `TEST_WEB_*` 覆盖基址；字段与 UAT 同构便于对齐用例 |
| `test_env` + `TEST_WEB_*` | 专用测试栈（`pytest --env=test_env`）；当前不提交独立 YAML | 通过 `TEST_WEB_BASE_URL` / `TEST_WEB_API_BASE_URL` 指定独立主机/API；端点必须在配置允许列表内 |
| [uat.yaml](uat.yaml) | UAT（`pytest --env=uat`） | 验收环境 |

## 数据隔离与功能一致性

- **功能一致性**：三套 YAML 中 `api.*`、`playwright.*` 等键对齐，差异主要在 `base_url` / `api_base_url` 与数据库连接。
- **数据隔离**：由 **不同主机、不同数据库、不同租户** 保证；本仓库只管理 URL 与连接串占位，不存放业务数据。
- **访问验证**：在本地配置 `.env`（参考仓库根目录 `.env.example`）后，使用 pytest 的 `--env` 选择配置环境：

```bash
pytest --env=test_env --collect-only
```

`test_env` 没有独立的已提交 YAML 时，由 `ConfigManager` 根据 `TEST_WEB_*` 环境变量构造配置；执行真实用例前必须确认网页/API 端点属于批准的 TEST/UAT 环境。

## Customer OpenAPI 本地凭证（可选）

- 单账户：复制 [customer_openapi.local.example.env](customer_openapi.local.example.env) 为 `customer_openapi.local.env`（已 gitignore），填写 `OPENAPI_APP_KEY` / `OPENAPI_APP_SECRET`。
- 多账户：复制 [customer_openapi.accounts.example.json](customer_openapi.accounts.example.json) 为 `customer_openapi.accounts.local.json`（`configs/*.json` 默认忽略，勿提交）。
- OpenAPI 凭证由对应的 API 客户端按需读取；相关比较和回归报告统一写入 `.runtime/reports/`（已 gitignore）。
