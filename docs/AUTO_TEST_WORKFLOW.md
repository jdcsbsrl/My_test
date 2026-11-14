---
title: auto_test 模块工作流程
purpose: 自动化测试执行、数据生命周期和报告
version: 3.1.0
updated: 2026-11-12
authority: 专项规范
---

# auto_test 模块工作流程

## 模块定位

`auto_test` 是自动化测试执行模块，负责配置测试环境、执行测试脚本、收集测试结果并生成可视化报告。

### 页面知识入口

- 客户报价明细的页面结构、赠品重复规则、新增/编辑及其 2.0 版本、复制和导入探索记录见 [CUSTOMER_QUOTATION_ITEM_AUTOTEST.md](CUSTOMER_QUOTATION_ITEM_AUTOTEST.md)。该文档标注了已观察结果、未确认的产品语义和未来回归门槛。
- 当前代码入口 `modules/auto_test/pages/customer_quotation_item_page.py` 提供目标页身份校验、只读观察和 `explored_flows()` 流程契约；写操作回归尚未启用。未来添加用例前应先读上述文档，并遵循本流程的数据生命周期和执行授权规则。

## 工作流程

### 流程架构

```
测试触发
     │
     ▼
┌─────────────────────┐
│ 环境配置阶段        │
│  验证环境           │
│  初始化数据工厂     │
│  注册生命周期回调   │
└───────┬─────────────┘
        │
        ▼
┌─────────────────────┐
│ 测试数据准备阶段    │
│  加载测试数据       │
│  生成动态数据       │
│  执行 setUp 任务    │
└───────┬─────────────┘
        │
        ▼
┌───────────────┐
│ 测试执行阶段  │
│  运行脚本    │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ 结果收集阶段  │
│  收集日志    │
└───────┬───────┘
        │
        ▼
┌─────────────────────┐
│ 测试数据清理阶段    │
│  级联删除测试数据   │
│  DB 兜底清理        │
└───────┬─────────────┘
        │
        ▼
┌───────────────┐
│ 报告生成阶段  │
│  可视化输出  │
└───────────────┘
```

### 阶段详细说明

#### 阶段1：环境配置与验证

**输入**: 环境配置文件（test.yaml/uat.yaml）

**处理步骤**:
1. 读取环境配置文件
2. 验证环境类型（test/uat）
3. 检查环境安全性（常规自动化回归禁止生产环境；生产数据专项任务只能走 [PROJECT_RULES.md](PROJECT_RULES.md) 规定的专用只读流程）
4. 验证API端点和认证信息
5. 初始化 TestDataFactory（注册数据生成器）
6. 初始化 TestDataLifecycleManager（注册 setUp/cleanup 回调）

**可访问知识库**:
- 自动化规范/*
- 测试规范/测试用例模板与优先级规则.json
- 业务规则/销售模块.json
- 业务规则/销售订单字段规范.json

**输出**: 环境验证报告

#### 阶段2：测试数据准备

**输入**: 测试数据文件 / 数据生成配置

**处理步骤**:
1. 使用 DataLoader 加载外部测试数据（JSON/YAML/CSV/Excel）
2. 使用 DynamicDataGenerator 生成动态数据（随机字符串/邮箱/手机号/关联数据）
3. 使用 DataVersionManager 管理数据版本（保存/回滚）
4. 执行 TestDataLifecycleManager.setup() 按拓扑序执行依赖任务

**关键工具**:
| 工具 | 用途 |
|------|------|
| DataLoader | 多格式文件加载，支持懒加载/流式模式避免OOM |
| DynamicDataGenerator | 带缓存的动态数据生成，支持依赖注入 |
| DataVersionManager | 测试数据文件版本控制 |
| TestDataLifecycleManager | 数据生命周期编排（拓扑排序执行setUp） |

**输出**: 就绪的测试数据

#### 阶段3：测试脚本执行

**输入**: 测试用例/测试脚本 + 准备就绪的测试数据

**处理步骤**:
1. 加载测试脚本
2. 初始化 Playwright 浏览器
3. 执行测试用例
4. 记录执行日志

**支持的测试类型**:
- UI自动化测试（Playwright）
- API接口测试
- 回归测试

**输出**: 测试执行日志

#### 阶段4：测试结果收集

**输入**: 测试执行日志

**处理步骤**:
1. 解析测试结果
2. 统计通过率/失败率
3. 收集失败截图和日志
4. 生成测试结果摘要

**输出**: 测试结果数据

#### 阶段5：测试数据清理

**输入**: 测试阶段创建的上下文数据

**处理步骤**:
1. 自动触发 TestDataLifecycleManager.execute_cleanup()
2. 按后创建先清理顺序执行 cleanup 任务
3. 如 API 清理失败，自动降级到 DB 直连兜底清理
4. 清理失败记录本次运行的证据并阻断成功结论，禁止扩大清理范围

**关键配置**:
- 生产环境（production）禁用 DB 兜底，防止数据风险
- 仅在批准的test/uat环境按已有所有权校验启用DB兜底，禁止清理其他运行的数据

**输出**: 清理操作日志

#### 阶段6：报告生成与展示

**输入**: 测试结果数据

**处理步骤**:
1. 生成 HTML 可视化报告
2. 生成 JSON 格式报告（便于集成）
3. （可选）需要通知时按独立通知能力发送结果；正式回归入口只生成报告并打印摘要，不包含通知步骤

**输出**: 测试报告（HTML/JSON），统一写入 `.runtime/reports/`。

## 支持的测试环境

正式回归会话仅接受 `test`、`uat`。配置管理器和部分 pytest 入口另支持 `test_env` 配置档，须验证具体入口和经批准的测试端点；这不改变项目入口中的环境红线或正式回归会话支持范围。

| 环境 | 配置文件 | 说明 |
|------|----------|------|
| test | configs/test.yaml | 内部测试环境 |
| uat | configs/uat.yaml | 用户验收测试环境 |

## 数据流转路径

```
测试配置 ──► 环境验证器 ──► 数据准备器 ──► 测试执行器 ──► 结果收集器 ──► 数据清理器 ──► 报告生成器
                │              │               │
                ▼              ▼               ▼
          TestDataFactory  DataLoader/    Playwright浏览器
          + Lifecycle     DynamicDataGen
              回调注册         + VersionMgr
```

## 关键操作步骤

### UI 自动化入口与浏览器选择

1. 先确认用户授权、`test`/`uat` 环境及目标账号角色，检查已有测试入口、页面对象、浏览器驱动、登录 fixture 和角色配置；优先复用适用的项目能力。没有覆盖时说明缺口，再决定如何补充。
2. 用户未指定浏览器时，优先使用项目框架管理的独立浏览器会话；任务需要使用用户现有浏览器时，先确认目标及操作范围。用户明确指定浏览器时遵循其选择；若无法与框架连接或复用会话，说明已确认的限制和可选方案，未经用户同意不切换浏览器。
3. 登录受阻时，先检查目标环境和目标角色的已有登录链路及安全配置；通用账号或其他角色登录失败不能证明目标角色登录失败。不得输出账号密码、Token、Cookie 等认证信息。
4. 登录会话受进程和浏览器上下文边界约束，不能假定独立 `auto_login` 进程或另一个浏览器的登录态已传给目标页面。无法安全建立目标会话时如实报告阻塞，不以手动登录替代已有可用链路。

### 预览回归范围

正式回归入口是 `tools/run_regression.py`。默认只计算范围和生成计划，不执行测试：

```powershell
python tools/run_regression.py --env test --scope module
python tools/run_regression.py --env test --case-id CASE-ID
python tools/run_regression.py --env test --requirement-id REQ-DEMO --impact-query "销售订单查询完整业务规则"
```

### 执行所选范围或已登记用例

确认环境、范围和当前任务的授权后，显式增加 `--execute` 才会执行：`--case-id` 运行登记表中关联的 pytest 节点，`--scope` 运行该范围的业务查询。

```powershell
python tools/run_regression.py --env test --case-id CASE-ID --execute
python tools/run_regression.py --env test --scope module --execute
```

`--execute` 只控制程序是否运行，不构成用户授权。

两种入口的执行路径不同：`--scope` 通过 `regression_session` 执行只读业务查询并生成报告；`--case-id` 和 `--impact-query` 运行登记表关联的 pytest 节点，由测试框架管理用例数据生命周期和执行证据。两条路径都执行环境与授权校验，也都不会把自然语言用例自动编译为测试脚本。

### Python 调用

需要在 Python 中集成回归报告时，使用当前报告工具的实际 API：

```python
from tools.report_generator import run_regression_tests

report = run_regression_tests(env_name="test", scope="module")
print(report.summary())
```

HTML 和 JSON 报告由 `run_regression_tests()` 统一写入 `.runtime/reports/`，不需要手动拼接输出路径。

### 执行流程

1. **校验环境**：只允许 `test` 或 `uat`，并检查端点是否在允许列表内；
2. **选择用例**：按 smoke、module、release、用例 ID 或知识库影响范围计算执行计划；
3. **准备会话和数据**：由当前回归会话与数据生命周期组件负责；
4. **执行脚本**：运行登记表中明确关联的 pytest 节点；
5. **收集结果**：记录通过、失败、跳过、阻断和执行证据；
6. **生成报告**：通过 `TestReportGenerator` 写入 `.runtime/reports/`；
7. **发布门禁**：由 `ReleaseQualityGate` 根据完整性和回归结果给出交付决定。

## 异常处理

| 异常场景 | 处理策略 |
|----------|----------|
| 环境配置错误 | 抛出异常并提示配置问题 |
| 测试脚本失败 | 记录失败日志和截图 |
| 网络超时 | 重试机制（最多3次） |
| 认证失败 | 提示检查凭证 |

## 输出格式规范

### HTML报告格式
- 文件名: `regression_report_<日期>_<时间>.html`
- 内容: 测试概览、详细结果、失败截图、统计图表

### JSON报告格式
- 文件名: `regression_report_<日期>_<时间>.json`
- 内容: 结构化测试结果数据

### 报告内容
- 测试执行时间
- 用例总数/通过数/失败数
- 通过率统计
- 失败用例详情
- 执行耗时分析

## 个人回归入口与结果可信度

`python tools/run_regression.py --env test --scope smoke --execute` 验证基础查询、精确筛选和状态筛选；`--scope module --execute` 增加模糊筛选、组合筛选、空结果和分页检查；`--scope release --execute` 执行模块全部查询契约，供发布门禁使用。不带 `--execute` 时只输出计划。
执行需已有明确授权。数据不足返回BLOCKED，不用空列表证明筛选正确；HTTP成功码不能代替业务断言。
返回码0表示所选范围全部通过，1表示失败，2表示验证不完整。报告展示计划数、实际执行数、跳过和阻断。
 pytest核心/P0用例跳过时不得返回成功；仅包含非核心可选用例的全跳过 shard 记录为验证不完整但不以退出码2阻断，setup/teardown错误进入运行摘要。

登记用例通过 `--case-id` 选择，默认预览，增加 `--execute` 执行；同一需求下的活动 P0 用例会自动补入选择范围，不能通过缩小参数绕过核心场景；结果保留执行时的版本及证据。
规则变更可使用 `--requirement-id <需求ID> --impact-query <完整规则检索词>` 计算受影响用例；影响用例及同需求 P0 会进入预览，确认后再加 `--execute`。
UI自愈事件进入运行报告并标记需复核定位器，高风险动作同时检查操作名及定位描述。
定位成功不等于业务成功，页面用例仍须保留业务后置断言。

核心流程的数据创建和清理继续使用TestDataLifecycleManager的run_id、worker_id、tenant_id所有权边界。
本次入口不自动造数，不修改共享数据。数据不足暴露为验证不完整，由批准的数据准备步骤解决。

## 命令行会话与登记用例报告

回归入口优先使用当前环境提供的Token和clientid；缺少任一项时，用环境账号进行浏览器登录并在内存中取得API会话。
不再要求用户手工提取加密密钥；会话结束清除HTTP认证和Cookie，不保存认证文件。已提供但失效的Token仍按真实失败报告，不无条件重试业务请求。
`python tools/auto_login.py --env uat`默认检查浏览器会话；`--method api`保留需要完整加密配置的原API登录方式。
单独运行登录工具不会给后续进程持久化Token；后续回归入口自行建立会话。

登记用例执行前校验脚本路径、函数节点和已有指纹。每项最多执行600秒，超时、缺失/损坏XML或跳过均不能算通过。
执行证据和汇总HTML/JSON进入`.runtime/reports/registered/<run_id>/`，登记表保存执行时的用例ID、版本及证据路径。
浏览器定位变更契约通过本地HTML故障注入验证：旧定位失效后可通过唯一语义定位继续；多个候选时阻断；替代成功仍记录待复核事件并保留业务断言。

## 销售订单排序审计（auto_test 模块）

排序审计的业务逻辑、测试、命令入口和报告生成全部位于 `modules/auto_test/`，不依赖 `tools/` 下的草稿脚本。预览执行范围：

```powershell
python -m modules.auto_test sort-audit --env test
```

确认环境和授权后执行 13 个启用字段的升序、降序审计（利润因业务状态暂缓，单独核查使用 --field 利润）：

```powershell
python -m modules.auto_test sort-audit --env test --execute --page-size 250 --max-pages 3
```

审计只读订单列表、订单明细及字段映射接口，不创建或修改订单。报告写入 `.runtime/reports/sales_order_sort/`，包含 JSON 和 Markdown。PASS 表示排序依据可验证且样本符合规则；WARNING 表示样本或排序依据不足，不能据此判为缺陷，WARNING 不阻断（审计器退出码 0）；确认失败返回退出码 1；FAIL 仅表示依据明确且存在可复现逆序或空值未置后的情况。数据库 `en_US.utf8` 文本 collation 尚未在审计器中复刻时，店铺名、物流渠道名和物流单号的字符串单调性记为 WARNING，不按 Python Unicode 码点序判缺陷，但空值位置仍可独立验证。模块命令和离线单元测试已具备；真实 TEST ERP 排序审计的 CI 任务尚未接入，需确认报告流转目标后再添加独立的非阻断任务。

## 销售订单交货状态筛选回归（auto_test 模块）

需求 1003062 的只读筛选检查由 `modules/auto_test/core/sales_order_delivery_status_regression.py` 实现，离线单元测试保留在 `tests/unit/`。默认只预览 test 环境、四种状态和分页参数：

```powershell
python -m modules.auto_test delivery-status-regression --env test
```

获得测试执行授权并确认环境后，显式添加 `--execute` 才会向 test/uat 的销售订单列表接口发送查询请求。可用 `--flags`、`--page-size` 和 `--max-pages` 限定检查范围：

```powershell
python -m modules.auto_test delivery-status-regression --env test --execute --flags 0,10,30,20 --page-size 500 --max-pages 100
```

每种状态分别检查返回行的 `deliveryStatus`，重点验证搜索结果与请求状态精确匹配。分页结果按 `orderNo` 检查重复；多页结果缺少订单编号或出现重复时，不得判为完整通过。`交运中` 是中间状态，完整查询返回空结果记为 `EMPTY_OK`，整体可以通过；这不表示有订单行可供状态核对。未交运、交运成功、交运失败的空结果仍记为 `NO_SAMPLE`，需要样本才能确认筛选精度。分页上限不足记为 `PARTIAL`，接口或响应无法验证时记为 `BLOCKED`。报告写入 `.runtime/reports/sales_order_delivery_status/` 的 JSON 文件。正常状态的结果通过，且交运中为 `PASS` 或 `EMPTY_OK` 时返回码 0；确认失败返回码 1，验证不完整返回码 2。CI 在组长账号测试通道运行真实 TEST 环境回归，离线单元测试继续由 `tests/unit/` 执行。

## 需求 1003531 库存 SKU 与销售订单导出回归

`modules/auto_test/tests/test_export_requirement_1003531.py` 同时支持 test 和 uat 配置。管理员 CI 分片只在 test 环境执行 `-m "not slow"`，覆盖库存 SKU 超 5000 条分页实时导出、固定底部按钮，以及库存 SKU 和销售订单从列表直接传查询条件创建导出任务。CI 创建的任务使用 `CI_R1003531_` 前缀，便于在共享任务列表识别来源。

TEST 环境的导出任务定时器不是持续运行，依赖后台任务完成和文件下载的库存全分页对账、销售订单实时文件与异步文件对账统一标记为 `slow`，不进入普通 CI，也不影响合并门禁。人工开启定时器后执行：

```powershell
pytest modules/auto_test/tests/test_export_requirement_1003531.py -m slow --env test
```

如后台任务需要更长时间，可通过 `EXPORT_TASK_TIMEOUT_MS` 调整等待上限。UAT 仅保留配置能力，不配置 CI 执行入口。
