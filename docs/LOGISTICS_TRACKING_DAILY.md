# ERP 与 17TRACK 轨迹抽查（本地按需执行）

此项抽查只在用户明确提出时从本机运行。仓库不再配置 GitHub Actions 定时或手动工作流；不会由提交、推送或其他 CI 事件触发。

## 本地执行

在项目根目录读取 `AGENTS.md` 和适用规范，核对 Git 状态。确认用户授权本次生产只读抽查后，从项目 `.env` 读取 `ERP_PROD_USERNAME`、`ERP_PROD_PASSWORD`。如需邮件发送，还需 `QQ_SMTP_AUTH_CODE` 和 `REPORT_EMAIL_TO`。凭证、令牌和邮件授权码不得输出到日志或报告。

本地抽查入口：

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
python tools/run_logistics_tracking_daily.py
```

运行成功后，报告写入 `workspace/YYYYMMDD/`，完整明细写入 `data/private/`。两处历史文件均保留，不自动清理。仅在用户已授权发送邮件且报告审核完成后，运行：

```powershell
python tools/send_logistics_tracking_email.py
```

## 查询边界与判定

- 生产 ERP 仅通过登录页面调用 `auth/login`，随后仅调用 `system/salesOrderLogisticsTracking/listNew` 进行只读查询；不得修改 ERP 数据或调用其他生产 API。
- 抽样排除 AF（收到信息）和 CC（成功签收），从不同状态、物流渠道和物流日期中选取 10 个真实且去重的运单。现有脚本对 ND、DD、AD、NF 的较早、较近日期窗口分别只扫描第 1 页；报告必须说明该限制及失败范围。
- 17TRACK 使用公开网页核对。出现验证码、权限限制或页面变化时停止自动交互，并如实记录未完成结果。
- 17TRACK 进度领先 ERP 为“系统落后（重点）”，尤其 17TRACK 已签收而 ERP 未签收；ERP 进度领先为“提醒（系统超前）”；异常状态不能线性比较时标为“状态差异待复核”。首次差异需人工复核，不直接认定为缺陷。

此生产只读抽查是用户曾明确批准的特例，不调用项目普通 UAT 回归入口。每次执行仍以用户当次指令为准。
