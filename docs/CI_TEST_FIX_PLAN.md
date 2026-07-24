# CI 单元测试失败修复计划

## 一、问题描述

GitHub Actions 单元测试执行失败，共 2 个测试用例失败：

| 测试用例 | 错误信息 |
|---------|---------|
| `test_audit_disabled` | `TypeError: AuditResult.__init__() got an unexpected keyword argument 'passed'` |
| `test_query_logs` | `sqlite3.OperationalError: near "limit": syntax error` |

## 二、根本原因分析

### 问题 1：`AuditResult` 初始化参数错误

**文件**: `modules/trae_test/orchestrator/audit_gateway.py` (第 67 行)

```python
# 当前代码（错误）
return AuditResult(passed=True, execution_time=0.0, audit_type=audit_type)
```

**原因**: `AuditResult` 的 `passed` 已重构为 `@property`（动态计算），不再是 dataclass 字段。直接在构造函数中传递 `passed=True` 会导致 `TypeError`。

### 问题 2：SQLite 查询语法错误

**文件**: `modules/trae_test/orchestrator/audit_logger.py` (第 277 行)

```python
# 当前代码（错误）
sql = f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
```

**原因**: SQLite 的 `LIMIT` 和 `OFFSET` 子句不支持命名参数（`LIMIT :limit`），只能使用位置参数。虽然代码尝试将 `:` 替换为 `?`，但这种替换是全局的，且 SQLite 对这些子句的参数化支持有限。

## 三、具体修复方案

### 修复 1：`AuditResult` 初始化方式

**文件**: `modules/trae_test/orchestrator/audit_gateway.py`

将：
```python
return AuditResult(passed=True, execution_time=0.0, audit_type=audit_type)
```

改为：
```python
result = AuditResult(execution_time=0.0, audit_type=audit_type)
result.passed = True  # 通过 setter 设置
return result
```

### 修复 2：SQLite 查询参数化

**文件**: `modules/trae_test/orchestrator/audit_logger.py`

将 SQLite 查询中的 `LIMIT :limit OFFSET :offset` 改为直接字符串拼接（仅用于数字参数，安全）：

```python
if self._use_pg:
    sql = f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
else:
    sql = f"SELECT * FROM audit_logs WHERE {where_clause} ORDER BY timestamp DESC LIMIT {limit} OFFSET {offset}"
```

## 四、实施步骤

| 步骤 | 操作 | 文件 |
|------|------|------|
| 1 | 修改 `audit_gateway.py` 第 67 行 | `modules/trae_test/orchestrator/audit_gateway.py` |
| 2 | 修改 `audit_logger.py` 第 277-279 行 | `modules/trae_test/orchestrator/audit_logger.py` |
| 3 | 本地运行失败测试用例验证 | `pytest tests/unit/test_audit_gateway.py::TestAuditGateway::test_audit_disabled tests/unit/test_audit_gateway.py::TestAuditGateway::test_query_logs` |
| 4 | 全量单元测试验证 | `pytest tests/unit/` |
| 5 | 提交并推送到 GitHub | `git commit -m "fix: CI test failures - AuditResult init + SQLite query"` |

## 五、预期效果

| 验证项 | 预期结果 |
|--------|---------|
| `test_audit_disabled` | 测试通过 |
| `test_query_logs` | 测试通过 |
| 全量单元测试 | 全部通过（281 个测试） |
| GitHub Actions | 执行成功 |

## 六、风险评估及应对措施

| 风险 | 可能性 | 影响 | 应对措施 |
|------|--------|------|----------|
| `AuditResult.passed = True` 在某些场景下被覆盖 | 低 | 中 | `passed` setter 会设置 `_forced_passed`，优先于动态计算 |
| SQLite 查询 SQL 注入 | 低 | 高 | `limit` 和 `offset` 都是整数参数，已通过类型检查 |
| 其他代码也使用了 `AuditResult(passed=...)` | 中 | 高 | 全局搜索并修复所有类似用法 |

## 七、关于 `configs/__init__.py`

**问题**: 用户询问 `configs/__init__.py` 的 git 变更区是什么。

**分析**: 该文件可能是：
1. **未追踪文件**（首次修改但未 `git add`）
2. **已修改但未提交**（`git status` 显示在 `Changes not staged for commit`）
3. **已暂存但未提交**（`git status` 显示在 `Changes to be committed`）

**建议**: 运行 `git status` 查看该文件的具体状态，确认是否需要加入此次提交。
