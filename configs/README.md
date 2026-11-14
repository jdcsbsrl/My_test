# 运行环境配置说明

| 配置来源 | 用途 | 与 UAT 关系 |
|-----------|------|----------------|
| [test.yaml](test.yaml) | 默认自动化（`pytest --env=test`） | 可通过 `TEST_WEB_*` 覆盖基址；字段与 UAT 同构便于对齐用例 |
| `test_env` + `TEST_WEB_*` | 测试环境的额外配置档（部分 pytest 入口支持）；不是新增业务环境，也未提交独立 YAML | 通过 `TEST_WEB_BASE_URL` / `TEST_WEB_API_BASE_URL` 配置测试端点；端点必须属于批准的测试环境且通过允许列表校验 |
| [uat.yaml](uat.yaml) | UAT（`pytest --env=uat`） | 验收环境 |

## 数据隔离与功能一致性

- **功能配置**：`test` 和 `uat` 使用各自的 YAML；`test_env` 在没有独立 YAML 时由环境变量构造，并非第三套 YAML。
- **数据隔离**：取决于实际部署的主机、数据库和租户；配置档名称或不同 URL 本身不能证明数据隔离。
- **访问验证**：在本地配置 `.env`（参考仓库根目录 `.env.example`）后，使用 pytest 的 `--env` 选择配置环境：

```bash
pytest --env=test_env --collect-only
```

`test_env` 没有独立的已提交 YAML 时，由 `ConfigManager` 根据 `TEST_WEB_*` 环境变量构造配置；其默认允许的源与 `test` 相同，但配置和凭据来源不一定相同，不能视为完全等价。正式回归命令只接受 `test`、`uat`；执行真实用例前必须确认网页/API 端点属于批准的测试环境。

## Customer OpenAPI 本地凭证（可选）

- 单账户：复制 [customer_openapi.local.example.env](customer_openapi.local.example.env) 为 `customer_openapi.local.env`（已 gitignore），填写 `OPENAPI_APP_KEY` / `OPENAPI_APP_SECRET`。
- 多账户：复制 [customer_openapi.accounts.example.json](customer_openapi.accounts.example.json) 为 `customer_openapi.accounts.local.json`（`configs/*.json` 默认忽略，勿提交）。
- OpenAPI 凭证由对应的 API 客户端按需读取；相关比较和回归报告统一写入 `.runtime/reports/`（已 gitignore）。
