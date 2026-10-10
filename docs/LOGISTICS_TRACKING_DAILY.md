# ERP 与 17TRACK 每日轨迹抽查

本任务独立于 Codex，由 GitHub Actions 的 `.github/workflows/erp-17track-daily.yml` 运行。
每天北京时间 15:31 左右触发，也可在 Actions 页面手动运行。定时任务可能延迟，只在默认分支触发。

## 公有仓库启用

在仓库 Settings → Secrets and variables → Actions 中配置以下 **Repository secrets**：

| Secret | 用途 |
|---|---|
| `ERP_PROD_USERNAME` | ERP 生产只读登录账号 |
| `ERP_PROD_PASSWORD` | ERP 生产登录口令 |
| `QQ_SMTP_AUTH_CODE` | QQ 邮箱 SMTP 授权码，不是邮箱登录密码 |
| `REPORT_EMAIL_TO` | 收件邮箱，同时作为 QQ SMTP 发件邮箱 |
| `ERP_17TRACK_HISTORY_KEY` | 至少 32 个字符的随机密钥，用于给运单号做 HMAC 去重 |

建议使用密码管理器生成并长期保存 `ERP_17TRACK_HISTORY_KEY`。更换此密钥后，旧历史哈希无法用于去重；需同时重建历史种子。可选 Secret `ERP_17TRACK_PRIOR_HASHES` 是首次云端运行的本机历史去重种子。**不填也能运行**，但首轮可能再次抽到此前本机抽查的单号。设置后，云端每次成功运行都会自动累积和恢复哈希历史，无须手动更新此 Secret。

本机生成可选种子：把上面的密钥临时设为当前进程环境变量后，执行
`python tools/run_logistics_tracking_daily.py --export-seed --archive .runtime/cache/logistics_tracking_ci_seed`。
生成的 `.runtime/cache/logistics_tracking_prior_hashes_YYYYMMDD.txt` 内容可复制到 `ERP_17TRACK_PRIOR_HASHES`，文件本身不能提交。
该命令只读本机 `data/private/logistics_tracking_*.csv`，不访问 ERP 或 17TRACK。
导出时必须设置**同一** `ERP_17TRACK_HISTORY_KEY`，否则会生成不兼容的普通 SHA-256 哈希。
密钥与种子都不能写入代码、工作流 YAML、提交记录或 Actions 日志。

把本工作流、脚本和文档提交到默认分支后，先在 Actions 页面手动运行一次，核对收件邮箱中的报告。GitHub 托管 runner 的网络出口与本地不同，可能遇到登录、17TRACK 页面或 QQ SMTP 访问限制。此前仅完成本地发信模拟；云端首轮仍须实测。

## 查询边界

- 生产 ERP 仅通过登录页面调用 `auth/login`，随后仅向 `system/salesOrderLogisticsTracking/listNew` 发起只读查询，不调用其他生产 API。
- 查询 ND、DD、AD、NF 四种状态；每种状态分别扫描较早、较近物流日期窗口的第一页。AF 和 CC 不纳入抽样。分层失败会写入报告，不补造数据。
- 每轮从真实且未使用的单号中抽 10 个，优先覆盖不同状态、渠道和较早仍未签收的运单。
- 17TRACK 通过公开网页查询。验证码、权限限制或页面变化导致无法验证时立即停止，不绕过限制。

## 邮件、产物和历史

完整运单号、ERP 状态、17TRACK 状态和差异明细只在本次 runner 的 `workspace/YYYYMMDD/` 报告和 `data/private/` CSV 中生成，并通过 QQ SMTP 把完整 Markdown 报告作为附件直接发送到 `REPORT_EMAIL_TO`。邮件正文列出差异单号和两侧状态。若抽查失败但产生报告，仍发送不完整报告；邮件发送失败则 Actions 失败。GitHub Actions 的公开日志不输出完整报告、密码或令牌。

公有仓库的 Actions 产物 **只上传 HMAC-SHA256 去重历史** `history.json`，不上传报告、CSV 或原始运单号。该产物可被有仓库读取权限的人下载；没有密钥时不能直接从哈希读出运单号。成功运行时自动更新历史，下一轮自动恢复。产物保留 90 天；如果历史丢失或过期，工作流停止并要求恢复历史，防止重复抽样。

该生产只读任务是用户明确批准的特例，不调用项目普通 UAT 回归入口，不创建、清理或修改 ERP 数据。差异只作为复核线索。
