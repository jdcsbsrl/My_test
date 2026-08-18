# 使用示例

本文档提供 Test ERP 项目的常用命令示例，帮助用户快速上手多Agent协同工具。

---

## 前提条件

在执行以下命令前，请确保：

1. 已激活 Python 虚拟环境
2. 当前目录为项目根目录 `d:\Working\test_erp`

```powershell
# 激活虚拟环境
.venv\Scripts\Activate.ps1
```

---

## 1. 测试用例生成（带全程审核）

生成测试用例时，系统会自动调用 AuditAgent 进行全程审核，确保用例格式、字段、命名等符合规范。

```powershell
python tools/multi_agent_runner.py --task test_case --requirement-id 1001345 --requirement-name "客户报价明细导出优化"
```

**参数说明**：
- `--task test_case`: 指定任务类型为测试用例生成
- `--requirement-id`: 需求ID
- `--requirement-name`: 需求名称

**输出位置**: `workspace/YYYYMMDD/` 目录。

---

## 2. 代码审核（5种审核全覆盖）

对指定文件进行全面代码审核，涵盖以下5种审核类型：

| 审核类型 | 说明 |
|---------|------|
| 测试用例审核 | 格式、字段、命名、路径 |
| 代码规范审核 | 编码规范、代码风格、最佳实践 |
| 环境审核 | 依赖配置、环境变量、权限设置 |
| 影响分析 | 代码变更影响范围、兼容性测试 |
| 安全审核 | 敏感信息、数据保护、合规性 |

```powershell
python tools/multi_agent_runner.py --task code_review --file modules/trae_test/utils/test_case_generator.py
```

**参数说明**：
- `--task code_review`: 指定任务类型为代码审核
- `--file`: 待审核的文件路径

---

## 3. 全能审核（4种审核类型）

对整个项目执行全能审核，自动检测项目中的潜在问题。

```powershell
python tools/multi_agent_runner.py --task full_audit
```

**参数说明**：
- `--task full_audit`: 指定任务类型为全能审核

---

## 4. 项目结构审核

验证项目是否符合 HarnessEngineer 架构规范，检查目录结构、文件命名等。

```powershell
python tools/project_structure_auditor.py
```

**输出内容**：
- 目录结构验证结果
- 必要文件存在性检查
- 架构合规性报告

---

## 5. 交互模式

启动交互式命令行界面，通过菜单选择要执行的任务。

```powershell
python tools/multi_agent_runner.py --interactive
```

**交互模式特点**：
- 提供友好的菜单界面
- 支持逐步输入参数
- 适合不熟悉命令行参数的用户

---

## 常见问题

### Q: 命令执行失败怎么办？

1. 确认虚拟环境已激活
2. 检查依赖是否完整安装：`pip install -r requirements.txt`
3. 查看错误日志获取详细信息

### Q: 审核不通过如何处理？

AuditAgent 会提供详细的错误反馈和修正建议，根据建议修改后重新执行即可。默认支持3次重试。

### Q: 输出文件在哪里？

生成文件默认保存在 `workspace/YYYYMMDD/` 目录下。

---

## 相关文档

- [工作流程总览](WORKFLOW.md)
- [多Agent协同模块](../modules/trae_test/orchestrator/)
- [Agent 规则](AGENT_RULES.md)
