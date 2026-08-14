---
alwaysApply: false
description: 智能体配置与交互规则
---
# 智能体配置与交互规则

> 版本：v3.0
> 生效日期：2026-07-16
> 维护人：Test ERP Team

---

## 一、智能体列表

| 智能体名称 | 职责 | 访问权限 |
|-----------|------|----------|
| TestCaseGenerator | 测试用例生成 | 业务规则/*, 测试规范/*, 导航规范/* |
| AutoTestExecutor | 自动化测试执行 | 自动化规范/*, 测试规范/模板规则, 业务规则/销售模块 |
| KnowledgeRetriever | 知识检索 | 全部知识库 |
| ReportGenerator | 报告生成 | 测试结果数据 |
| AuditAgent | 审核监督 | 全部知识库 |

---

## 二、智能体交互规则

### 1. 测试用例生成智能体 (TestCaseGenerator)

**职责**: 基于用户需求和知识库，自动生成符合标准的测试用例，并进行质量评分与优化

**工作流程**:
1. 接收用户测试需求
2. 检索相关业务规则知识库
3. 分析业务流程和边界条件
4. 按15字段模板生成测试用例
5. 使用 `TestCaseScoreEngine` 对每条用例进行五维度质量评分
6. 使用 `TestCaseOptimizer` 自动优化低分用例（补充步骤/预期结果/用例名称）
7. 使用 `TestCaseRegenerationLoop` 执行自动重生闭环（最多3次，熔断保护）
8. 标记 `needs_human_review` 的用例提交人工审查
9. 导出优化后的测试用例（Excel/JSON），含质量评分列

**关键工具 v3.0**:
| 工具 | 用途 |
|------|------|
| TestCaseGenerator | 按15字段模板生成测试用例 |
| TestCaseScoreEngine | 五维度评分（覆盖率/完整性/优先级/可执行性/可维护性） |
| TestCaseOptimizer | 自动优化步骤、预期结果、用例名称 |
| TestCaseRegenerationLoop | 自动重生闭环 + 熔断机制（最大3次，冷却期3600s） |

**访问控制**:
- ✅ 业务规则目录（全部）
- ✅ 测试规范目录（全部）
- ✅ 导航规范目录（全部）
- ✅ modules/trae_test/utils/test_case_strategy.py（评分/优化/重生工具）
- ❌ 自动化规范目录（禁止）

### 2. 自动化测试执行智能体 (AutoTestExecutor)

**职责**: 执行自动化测试脚本，管理测试数据生命周期，收集并分析测试结果

**工作流程**:
1. 验证测试环境配置，初始化 TestDataFactory
2. 注册 TestDataLifecycleManager 的 setUp/cleanup 回调
3. 使用 DataLoader 加载外部测试数据（JSON/YAML/CSV/Excel）
4. 使用 DynamicDataGenerator 生成动态测试数据
5. 使用 DataVersionManager 管理数据版本
6. 执行 setUp 任务（拓扑排序自动处理依赖）
7. 加载并执行测试脚本
8. 收集执行结果和截图
9. 执行 cleanup 任务（级联删除 + DB 兜底清理）
10. 生成测试报告

**关键工具 v3.0**:
| 工具 | 用途 |
|------|------|
| DataLoader | 多格式文件加载，支持懒加载/流式模式 |
| DynamicDataGenerator | 动态数据生成（随机字符串/邮箱/手机号/关联数据） |
| DataVersionManager | 测试数据文件版本控制 |
| TestDataLifecycleManager | 数据生命周期编排（拓扑排序setUp + 级联cleanup + DB兜底） |
| TestDataFactory | 统一数据工厂入口 |

**访问控制**:
- ✅ 自动化规范目录（全部）
- ✅ 测试规范/测试用例模板与优先级规则.json
- ✅ 测试规范/已学习测试用例索引.json
- ✅ 业务规则/销售模块.json
- ✅ 业务规则/销售订单字段规范.json
- ✅ modules/auto_test/core/test_data_factory.py（数据加载/生成/版本管理）
- ✅ modules/auto_test/core/test_data_lifecycle.py（生命周期管理）
- ❌ 其他业务规则（禁止）
- ❌ 导航规范（禁止）

### 3. 知识检索智能体 (KnowledgeRetriever)

**职责**: 为其他智能体提供知识库检索服务

**工作流程**:
1. 接收检索请求
2. 根据权限验证访问范围
3. 检索匹配的知识内容
4. 返回过滤后的知识结果

**访问控制**:
- ✅ 全部知识库目录

### 4. 报告生成智能体 (ReportGenerator)

**职责**: 生成可视化测试报告

**工作流程**:
1. 接收测试结果数据
2. 统计分析测试结果
3. 生成 HTML/JSON 格式报告
4. 输出报告文件

### 5. 审核智能体 (AuditAgent)

**职责**: 监督其他Agent的工作流程，确保输出符合规范

**工作流程**:
1. 监控其他Agent的任务执行过程
2. 验证测试用例格式符合15字段标准模板
3. 验证知识库访问符合权限规则
4. 验证输出文件格式和命名规范
5. 生成审核报告和改进建议

**访问控制**:
- ✅ 全部知识库目录（用于验证权限）

**审核内容**:
- **测试用例格式审核**: 验证15字段标准模板、字段顺序、用例目录格式
- **测试用例质量审核**: 验证质量评分字段完整性，检查 needs_human_review 标记是否正确
- **知识库访问权限审核**: 验证Agent只能访问其权限范围内的知识库文件
- **输出格式审核**: 验证Excel/JSON文件格式、文件名命名规范

---

## 三、智能体协作机制

### 协作流程

```
用户请求
    │
    ▼
TestCaseGenerator ──► 生成测试用例
       │
       ▼
质量评分与优化 ◄── TestCaseScoreEngine
       │               + TestCaseOptimizer
       │               + TestCaseRegenerationLoop
       ▼
  ┌────┴────┐
  │ 通过    │ 未通过（needs_human_review → 人工审查）
  └────┬────┘
       │
       ▼
AutoTestExecutor ──► 数据准备（DataLoader/DynamicDataGen/VersionMgr）
       │               + 生命周期管理（setUp）
       │
       ▼
      执行测试
       │
       ▼
      数据清理（LifecycleManager.cleanup + DB兜底）
       │
       ▼
  ReportGenerator
       │
       ▼
      生成报告
```

### 任务分配机制

| 任务类型 | 负责智能体 | 触发条件 |
|----------|-----------|----------|
| 测试用例生成 | TestCaseGenerator | 用户提交测试需求 |
| 自动化测试执行 | AutoTestExecutor | 测试用例生成完成 |
| 知识检索 | KnowledgeRetriever | 其他智能体请求 |
| 报告生成 | ReportGenerator | 测试执行完成 |
| 审核监督 | AuditAgent | 测试用例生成完成、测试执行完成、输出文件生成完成 |

### 审核触发机制

审核Agent在以下关键节点自动触发：
1. **测试用例生成后**: 审核测试用例格式是否符合15字段标准模板
2. **知识库访问前**: 审核访问权限是否符合访问控制规则
3. **输出文件生成后**: 审核文件格式和命名规范

### 审核反馈流程

```
Agent执行任务
    │
    ▼
AuditAgent审核
    │
    ├── 通过 ──► 继续执行
    │
    └── 未通过 ──► 生成审核报告 ──► 返回改进建议 ──► 修正后重新审核
```

---

## 四、工具调用决策树（IF/THEN 规则）

### 4.1 TestCaseGenerator 工具调用决策

```
用户请求测试用例生成
    │
    ▼
IF 用户需求已明确
    │
    ├── THEN 使用 KnowledgeRetriever 检索业务规则知识库
    │
    ├── THEN 使用 TestCaseGenerator 按15字段模板生成测试用例
    │
    ├── THEN 使用 TestCaseScoreEngine 对每条用例评分
    │
    │   IF 评分 < 70
    │       │
    │       ├── THEN 使用 TestCaseOptimizer 优化该用例
    │       │
    │       └── THEN 重新评分
    │
    │   IF 优化后评分仍 < 70 且 未触发熔断
    │       │
    │       └── THEN 使用 TestCaseRegenerationLoop 执行自动重生
    │
    │   IF 评分 >= 70
    │       │
    │       └── THEN 标记为合格用例
    │
    │   IF needs_human_review = True
    │       │
    │       └── THEN 提交人工审查队列
    │
    └── THEN 导出优化后的测试用例（Excel/JSON），含质量评分列
```

### 4.2 AutoTestExecutor 工具调用决策

```
用户请求自动化测试执行
    │
    ▼
IF 测试环境配置有效
    │
    ├── THEN 初始化 TestDataFactory
    │
    ├── THEN 注册 TestDataLifecycleManager 的 setUp/cleanup 回调
    │
    │   IF 存在外部测试数据文件（JSON/YAML/CSV/Excel）
    │       │
    │       └── THEN 使用 DataLoader 加载（懒加载模式用于大文件）
    │
    │   IF 需要动态生成测试数据
    │       │
    │       └── THEN 使用 DynamicDataGenerator（启用缓存）
    │
    │   IF 需要版本追踪
    │       │
    │       └── THEN 使用 DataVersionManager 创建快照
    │
    ├── THEN 执行 setUp 任务（拓扑排序自动处理依赖）
    │
    ├── THEN 加载并执行测试脚本
    │
    ├── THEN 收集执行结果和截图
    │
    └── THEN 执行 cleanup 任务（级联删除 + DB兜底清理）
```

### 4.3 TestCaseScoreEngine 评分规则

```
执行评分
    │
    ▼
IF execution_count < 10（冷启动保护）
    │
    └── THEN 使用静态维度评分（覆盖率30% + 完整性25% + 优先级20% + 可维护性10%）
        │
        └── 跳过可执行性维度（无执行历史数据）
    │
    ELSE
    │
    └── THEN 使用全五维度评分：
        │
        ├── 覆盖率（30%）: 业务规则匹配度
        │
        ├── 完整性（25%）: 步骤/预期/前置条件完整性
        │
        ├── 优先级（20%）: 用例优先级权重
        │
        ├── 可执行性（15%）: 通过率 + 执行耗时
        │
        └── 可维护性（10%）: 步骤长度 + 重复度
```

### 4.4 TestCaseRegenerationLoop 熔断规则

```
执行自动重生
    │
    ▼
IF 同一用例在冷却期（3600秒）内重生次数 >= 3
    │
    └── THEN 触发熔断，标记为 needs_human_review = True
        │
        └── 停止自动重生，等待人工介入
    │
    ELSE
    │
    └── THEN 执行重生，增加重生计数
```

---

## 五、知识访问控制策略

### 访问控制目的

1. **防止信息过载**: 限制智能体仅能访问完成任务必需的知识
2. **避免无根据推测**: 基于明确的业务规则生成测试用例
3. **提高检索效率**: 缩小检索范围，加快知识定位

### 权限配置

```json
{
  "access_control": {
    "enabled": true,
    "module_access_rules": {
      "trae_test": [
        "业务规则/*",
        "测试规范/*",
        "导航规范/*"
      ],
      "auto_test": [
        "自动化规范/*",
        "测试规范/测试用例模板与优先级规则.json",
        "测试规范/已学习测试用例索引.json",
        "业务规则/销售模块.json",
        "业务规则/销售订单字段规范.json"
      ],
      "knowledge_retriever": [
        "业务规则/*",
        "测试规范/*",
        "自动化规范/*",
        "导航规范/*",
        "销售模块/*"
      ],
      "audit_agent": [
        "业务规则/*",
        "测试规范/*",
        "自动化规范/*",
        "导航规范/*",
        "销售模块/*"
      ]
    }
  }
}
```

### 访问控制执行流程

1. **请求接收**: 智能体发起知识访问请求
2. **权限验证**: 检查访问控制规则
3. **路径过滤**: 根据权限规则过滤可访问文件
4. **内容返回**: 返回符合权限的知识内容

---

## 六、审核Agent规范V2（严格执行）

### 5.1 审核Agent职责定位

**核心职责**:
- 对所有其他Agent的输出结果进行全面、严格的质量检查
- 确保所有智能体严格遵守既定工作流程
- 杜绝任何胡编乱造、擅自修改代码等违规行为
- 建立明确的审核标准、错误反馈机制和责任追究制度

**审核范围**:
- 所有Agent的输出文件
- 代码和工具的位置和规范
- 工作流程合规性
- 知识库访问权限

### 5.2 输出文件规范（必须严格执行）

#### 5.2.1 文件命名规范
**格式**: 需求{id}{需求名}.xlsx
- **{id}**: 需求ID（可选），如果有则包含
- **{需求名}**: 需求名称（必填）

**示例**:
- 需求1001236销售订单SKU图片显示.xlsx（有需求ID）
- 需求销售订单导出时间优化.xlsx（无需求ID）

**禁止**:
- 禁止使用旧的命名格式（如：`测试用例_<模块>_<日期>.xlsx`）
- 禁止使用.json、.md等其他格式
- 禁止文件名包含特殊字符（\ / : * ? " < > |）
- 禁止文件名过长（建议不超过100字符）

#### 5.2.2 输出位置规范
**统一位置**: `workspace/{YYYYMMDD}/{formal|draft}/`（相对于项目根目录；如需外置目录，请通过 `WORKSPACE_OUTPUT_DIR` 配置）

| 类型 | 路径 | 说明 |
|------|------|------|
| 正式成果 | `workspace/YYYYMMDD/formal/` | 审核通过的正式测试用例 |
| 草稿 | `workspace/YYYYMMDD/draft/` | 未经审核或待修改的草稿 |

**示例**:
- `workspace/20260513/formal/<需求名>.xlsx`（正式成果）
- `workspace/20260513/draft/<需求名>.xlsx`（草稿）

**禁止**:
- 禁止输出到output/、test_cases_output/、modules/trae_test/output/等其他目录
- 禁止在项目根目录创建输出文件
- 禁止输出到非formal/draft子目录

#### 5.2.3 文件格式规范
**必须**: 仅生成.xlsx格式Excel文件
**禁止**: 生成.json、.md、.csv等任何其他格式
**模板**: 必须使用统一的15字段标准模板（assets/templates/测试用例模板.xlsx）

#### 5.2.4 Excel内容规范
**必须包含**:
- 标准15字段表头（顺序必须正确）
- 用例内容与标题相符
- 数据完整性（无空行、无乱码）

**15字段标准顺序**:
1. 用例目录
2. 用例名称
3. 需求ID
4. 前置条件
5. 用例步骤
6. 预期结果
7. 用例类型
8. 用例状态
9. 用例等级
10. 创建人
11. 优先级
12. 是否可自动化
13. 关联缺陷ID
14. 回归测试标识
15. 知识库关联

### 5.3 代码和工具管理规范

#### 5.3.1 工具位置规范
**工具类**: 必须放在以下位置
- tools/ 目录：通用工具
- modules/trae_test/utils/ 目录：trae_test模块专用工具
- modules/auto_test/utils/ 目录：auto_test模块专用工具

**禁止**:
- 禁止在项目根目录创建工具类
- 禁止随意创建新的工具目录

#### 5.3.2 脚本位置规范
**脚本文件**: 必须统一管理
- tools/ 目录：可执行脚本
- scripts/ 目录（如需要）：辅助脚本

**禁止**:
- 禁止在项目根目录散落脚本文件
- 禁止创建generate_cases_*.py、manual_generate_*.py等零散脚本

#### 5.3.3 统一Excel生成工具
**必须使用**: 统一的Excel生成工具
**禁止**: 自行编写Excel生成代码
**目的**: 确保模板一致性、减少错误

### 5.4 审核标准和流程

#### 5.4.1 审核触发机制
**必须审核**: 所有输出文件必须经过审核Agent审核
**审核节点**:
1. 输出文件生成后立即审核
2. 审核不通过必须阻断任务继续
3. 修正后重新审核

#### 5.4.2 审核内容清单
**文件审核**:
- [ ] 文件命名符合规范
- [ ] 文件位置符合规范
- [ ] 文件格式为.xlsx
- [ ] Excel表头正确
- [ ] 字段顺序正确
- [ ] 内容与标题相符
- [ ] 数据完整

**代码审核**:
- [ ] 工具位置正确
- [ ] 脚本位置正确
- [ ] 使用统一Excel生成工具

#### 5.4.3 审核结果处理
**审核通过**:
- 记录审核结果
- 允许任务继续

**审核不通过**:
- 立即阻断任务继续
- 生成详细的审核报告
- 明确指出问题位置和原因
- 提供具体的修正建议
- 记录审核失败结果

### 5.5 错误反馈机制

#### 5.5.1 错误信息要求
**必须包含**:
- 错误代码（如 FILE_NAME_INVALID）
- 错误描述（清晰说明问题）
- 错误位置（文件路径、行号等）
- 修正建议（具体可操作）
- 相关规范引用

#### 5.5.2 反馈流程
1. 审核发现问题
2. 生成详细错误报告
3. 返回给任务发起方
4. 任务发起方修正问题
5. 重新提交审核
6. 审核通过后继续

### 5.6 责任追究制度

#### 5.6.1 审核记录
**必须记录**:
- 审核时间（精确到秒）
- 审核类型
- 审核对象
- 审核结果（通过/不通过）
- 问题描述
- 责任人
- 处理状态

#### 5.6.2 违规处理
**轻微违规**（首次、非故意）:
- 警告
- 要求学习规范
- 重新审核

**严重违规**（多次、故意、造成损失）:
- 记录在案
- 报告相关负责人
- 暂停相关权限
- 需人工审核通过后恢复

#### 5.6.3 问题溯源
**支持查询**:
- 按时间查询审核历史
- 按Agent查询审核记录
- 按问题类型统计
- 追溯问题根源

### 5.7 违规行为清单

**严重违规（必须禁止）**:
- 胡编乱造测试用例内容
- 擅自修改代码和工具
- 不使用统一Excel生成工具
- 审核不通过仍继续执行
- 故意违反规范

**一般违规（需要纠正）**:
- 文件命名不规范
- 输出位置错误
- 文件格式错误
- Excel内容不符合模板
- 代码和工具位置错误

### 5.8 审核Agent工作流程

```
Agent生成输出
    │
    ▼
AuditAgent接收
    │
    ▼
检查文件命名 ──► 不通过 ──► 记录+反馈+阻断
    │
    ▼
检查文件位置 ──► 不通过 ──► 记录+反馈+阻断
    │
    ▼
检查文件格式 ──► 不通过 ──► 记录+反馈+阻断
    │
    ▼
检查Excel内容 ──► 不通过 ──► 记录+反馈+阻断
    │
    ▼
检查代码规范（如适用） ──► 不通过 ──► 记录+反馈+阻断
    │
    ▼
记录审核结果
    │
    ▼
通过，允许继续
```

---

## 八、执行要求

### 6.1 强制执行
- 本规范v3.0自发布之日起强制执行
- 所有Agent必须严格遵守
- 审核不通过禁止继续执行

### 6.2 培训和学习
- 所有相关人员必须学习本规范
- 新成员入职必须学习本规范
- 定期回顾和更新规范

### 6.3 持续改进
- 定期评估规范执行情况
- 收集反馈意见
- 持续优化审核机制

---

## 九、完整工作流示例

### 7.1 测试用例生成完整流程示例

**用户请求**: "为销售订单创建功能生成测试用例"

**Step 1: Agent阅读AGENTS.md**
```
Agent读取 AGENTS.md
    │
    ├── 定位「测试用例生成」索引
    │       │
    │       └── 找到核心工具：TestCaseGenerator, TestCaseScoreEngine, 
    │            TestCaseOptimizer, TestCaseRegenerationLoop
    │
    ├── 定位「agent_rules.md」规则文件
    │       │
    │       └── 找到工具调用决策树和评分规则
    │
    └── 定位「TRAE_TEST_WORKFLOW.md」工作流程文档
            │
            └── 获取完整流程步骤
```

**Step 2: 知识检索**
```python
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
r = KnowledgeRetriever()
business_rules = r.search_business_rules("销售订单")
requirements = r.search_requirements("创建订单")
```

**Step 3: 生成测试用例**
```python
from modules.trae_test.utils.test_case_generator import TestCaseGenerator
generator = TestCaseGenerator()
test_cases = generator.generate(business_rules, requirements)
# 生成15字段标准格式测试用例
```

**Step 4: 质量评分（自动触发）**
```python
from modules.trae_test.utils.test_case_strategy import TestCaseScoreEngine
scorer = TestCaseScoreEngine()

for case in test_cases:
    score = scorer.score(case)
    case['quality_score'] = score
    case['needs_human_review'] = score < 70
    
# TC_001: 评分85 → 合格
# TC_002: 评分65 → 需要优化
# TC_003: 评分90 → 合格
```

**Step 5: 自动优化（自动触发）**
```python
from modules.trae_test.utils.test_case_strategy import TestCaseOptimizer
optimizer = TestCaseOptimizer()

# 优化低分用例
for case in test_cases:
    if case['quality_score'] < 70:
        optimized_case = optimizer.optimize(case)
        case['quality_score'] = scorer.score(optimized_case)
        # TC_002: 优化后评分75 → 合格
```

**Step 6: 自动重生（按需触发）**
```python
from modules.trae_test.utils.test_case_strategy import TestCaseRegenerationLoop
loop = TestCaseRegenerationLoop()

# 如果优化后仍不合格，触发重生（最多3次，熔断保护）
for case in test_cases:
    if case['quality_score'] < 70:
        regenerated = loop.regenerate(case)
        if regenerated:
            case = regenerated
            case['quality_score'] = scorer.score(case)
        else:
            # 熔断触发，标记需要人工审查
            case['needs_human_review'] = True
```

**Step 7: 导出测试用例**
```python
from modules.trae_test.utils.excel_generator import ExcelGenerator
excel_gen = ExcelGenerator()
excel_gen.generate(test_cases, output_path="workspace/20260716/formal/需求销售订单创建.xlsx")
# 导出的Excel包含：15字段标准模板 + quality_score列 + needs_human_review列
```

**Step 8: AuditAgent审核**
```
AuditAgent审核
    │
    ├── 文件命名：✓ 需求销售订单创建.xlsx
    ├── 文件位置：✓ workspace/20260716/formal/
    ├── 文件格式：✓ .xlsx
    ├── Excel表头：✓ 15字段正确
    ├── 质量评分字段：✓ quality_score列存在
    └── 审核通过 → 允许继续
```

### 7.2 自动化测试执行完整流程示例

**用户请求**: "执行销售订单创建测试用例"

**Step 1: 初始化数据工厂**
```python
from modules.auto_test.core.test_data_factory import TestDataFactory
from modules.auto_test.core.test_data_lifecycle import TestDataLifecycleManager

factory = TestDataFactory()
lifecycle = TestDataLifecycleManager()

# 注册生命周期回调
factory.set_lifecycle_manager(lifecycle)
```

**Step 2: 加载测试数据**
```python
# 使用DataLoader加载外部数据
loader = factory.get_data_loader()
test_data = loader.load("data/test_data/sales_order.json", mode="lazy")
# 大文件自动使用懒加载模式
```

**Step 3: 动态数据生成**
```python
# 使用DynamicDataGenerator生成动态数据
generator = factory.get_dynamic_generator()
dynamic_data = generator.generate({
    "type": "email",
    "count": 10,
    "cache": True
})
# 启用缓存避免重复生成
```

**Step 4: 数据版本管理**
```python
# 使用DataVersionManager创建快照
version_manager = factory.get_version_manager()
version_id = version_manager.create_snapshot("sales_order_test_data")
# 记录当前数据版本，便于回溯
```

**Step 5: 执行setUp（拓扑排序）**
```python
# 注册setUp任务（自动处理依赖）
lifecycle.register_set_up("create_customer", priority=1)
lifecycle.register_set_up("create_product", priority=1, dependencies=["create_customer"])
lifecycle.register_set_up("create_order", priority=2, dependencies=["create_product"])

# 拓扑排序执行
lifecycle.execute_set_up()
# 执行顺序：create_customer → create_product → create_order
```

**Step 6: 执行测试脚本**
```python
# 加载并执行测试脚本
from modules.auto_test.drivers import BrowserDriver
driver = BrowserDriver()
driver.execute_test("tests/sales_order_create_test.py")
```

**Step 7: 执行cleanup（级联删除）**
```python
# 注册cleanup任务
lifecycle.register_cleanup("delete_order", priority=1)
lifecycle.register_cleanup("delete_product", priority=2, dependencies=["delete_order"])
lifecycle.register_cleanup("delete_customer", priority=3, dependencies=["delete_product"])

# 级联删除（按优先级逆序）
lifecycle.execute_cleanup()
# 执行顺序：delete_order → delete_product → delete_customer

# DB兜底清理（如果级联删除失败）
lifecycle.fallback_cleanup()
```

**Step 8: 生成测试报告**
```python
from tools.report_generator import ReportGenerator
report_gen = ReportGenerator()
report_gen.generate(test_results, "workspace/20260716/formal/测试报告_销售订单创建.html")
```

### 7.3 关键规则摘要

| 规则 | 触发条件 | 自动行为 |
|------|----------|----------|
| 评分规则 | 生成用例后 | 自动执行五维度评分 |
| 优化规则 | 评分 < 70 | 自动调用TestCaseOptimizer |
| 重生规则 | 优化后仍 < 70 | 自动执行重生闭环（最多3次） |
| 熔断规则 | 重生次数 >= 3 | 触发熔断，标记needs_human_review |
| 冷启动保护 | execution_count < 10 | 跳过可执行性维度，使用静态评分 |
| 懒加载规则 | 文件大小 > 阈值 | DataLoader自动切换为懒加载模式 |
| 拓扑排序 | setUp任务有依赖 | 自动按Kahn算法排序执行 |
| 级联清理 | cleanup任务有依赖 | 自动按优先级逆序执行 |
| DB兜底 | 级联删除失败 | 自动执行DB兜底清理 |
