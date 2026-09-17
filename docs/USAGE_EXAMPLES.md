# 使用示例

本文档提供 Test ERP 当前正式入口的常用命令。测试用例生成、登记、影响分析和回归执行分别使用专用 CLI；旧的多 Agent 统一脚本不再作为项目入口。

## 前提条件

执行命令前请确保：

1. 已激活 Python 虚拟环境；
2. 当前目录为项目根目录 `D:\Working\test_erp`；
3. 自动化测试仅使用 `test` 或 `uat` 环境，并已获得执行授权。

```powershell
.venv\Scripts\Activate.ps1
```

## 1. 生成测试用例

正式生成入口会检索知识库，执行固定字段处理、质量整理和 AuditGateway 审核。只有通过发布门禁的结果才会导出 Excel。

```powershell
python tools/case_generator_cli.py generate `
  --module "销售" `
  --function "订单查询" `
  --priority P1 `
  --provider self-hosted-llm `
  --requirement "验证销售订单查询的正常、异常和边界场景"
```

需要登记到用例版本库时，必须同时提供稳定的需求 ID：

```powershell
python tools/case_generator_cli.py generate `
  --module "销售" `
  --function "订单查询" `
  --priority P1 `
  --requirement-id REQ-DEMO `
  --requirement "验证销售订单查询的正常、异常和边界场景" `
  --provider self-hosted-llm `
  --register
```

最终 Excel 写入 `workspace/YYYYMMDD/`，生成诊断和审核信息写入 `.runtime/reports/`。

## 2. 查看和维护用例版本

```powershell
# 查看某个需求的活动用例
python tools/case_generator_cli.py list-cases --requirement-id REQ-DEMO

# 查看历史版本
python tools/case_generator_cli.py list-cases --history

# 检查未执行、失败、失效脚本和相似用例
python tools/case_generator_cli.py health --requirement-id REQ-DEMO --stale-days 30

# 预览知识规则变化及受影响用例
python tools/case_generator_cli.py impact --requirement-id REQ-DEMO --query "销售订单查询完整业务规则"
```

`retire` 只停用活动版本，`update` 会创建新版本；历史版本不会自动删除。

## 3. 执行回归测试

默认只生成选择计划，不执行测试：

```powershell
python tools/run_regression.py --env test --scope module
python tools/run_regression.py --env test --case-id CASE-ID
python tools/run_regression.py --env test --requirement-id REQ-DEMO --impact-query "销售订单查询完整业务规则"
```

确认范围和环境后，显式增加 `--execute` 才执行已登记用例：

```powershell
python tools/run_regression.py --env test --case-id CASE-ID --execute
```

报告和执行证据写入 `.runtime/reports/`。禁止将报告或测试产物写入项目根目录或 `workspace/` 历史交付目录。

## 4. 结构和文档审核

```powershell
python tools/project_structure_auditor.py --json
python tools/doc_consistency_checker.py --json
python tools/scan_sensitive_artifacts.py
```

代码审核由 `AuditAgent` 和统一审核网关负责；不再通过旧的统一交互脚本调用。

## 常见问题

### Q：生成失败怎么办？

先查看命令输出的 `.runtime/reports/case_generation_*.json` 诊断文件。生成能力不足、知识依据缺失和审核阻断分别按诊断中的 `status`、`questions` 和 `release_decision` 处理，不能用通用测试步骤替代业务依据。

### Q：审核不通过怎么办？

根据审核问题补充需求正文、候选依据或用户业务依据，然后重新执行生成。固定字段和已明确的业务规则不需要重复确认。

### Q：输出文件在哪里？

最终测试用例位于 `workspace/YYYYMMDD/`；中间 JSON、评分轨迹、审核报告和临时 Excel 位于 `.runtime/`。

## 相关文档

- [工作流程总览](WORKFLOW.md)
- [测试用例生成工作流](TRAE_TEST_WORKFLOW.md)
- [自动化测试工作流](AUTO_TEST_WORKFLOW.md)
- [Agent 规则](AGENT_RULES.md)
