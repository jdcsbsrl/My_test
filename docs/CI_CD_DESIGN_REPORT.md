# Test ERP 项目架构审查与 CI/CD 设计报告

> **版本**: v1.0  
> **日期**: 2026-07-16  
> **状态**: 待审核  
> **作者**: Test ERP Team

---

## 一、架构审查发现

### 1.1 技术栈分析

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 语言 | Python | 3.12+ | 核心开发语言 |
| 构建工具 | uv/pip | - | 依赖管理 |
| 测试框架 | pytest | 8.0+ | 单元/集成测试 |
| UI自动化 | Playwright | 1.50+ | 浏览器自动化测试 |
| API测试 | requests | 2.32+ | HTTP请求 |
| 报告工具 | Allure | 2.13+ | 测试报告生成 |
| 代码质量 | ruff | 0.3+ | 代码检查 |
| 代码格式化 | black | 24.0+ | 代码格式化 |
| 类型检查 | mypy | 1.9+ | 静态类型检查 |
| 配置管理 | python-dotenv | 1.0+ | 环境变量管理 |
| 数据处理 | PyYAML, openpyxl | - | 数据文件处理 |
| 数据库 | PostgreSQL, SQLAlchemy | - | 数据存储 |
| 缓存 | Redis | 5.0+ | 缓存管理 |

### 1.2 模块划分

```
test_erp/
├── modules/
│   ├── trae_test/          # 测试用例生成模块
│   │   ├── core/           # 核心组件（DB池、缓存、迁移）
│   │   ├── orchestrator/   # 多Agent协同编排
│   │   └── utils/          # 工具函数（生成器、检索器、策略引擎）
│   └── auto_test/          # 自动化测试执行模块
│       ├── api/            # API封装层
│       ├── core/           # 核心组件（环境、数据工厂、生命周期）
│       ├── drivers/        # 浏览器/HTTP驱动
│       ├── facades/        # 业务逻辑门面
│       ├── pages/          # 页面对象模型（POM）
│       └── tests/          # 自动化测试脚本
├── tests/                  # 单元/集成测试
│   ├── unit/               # 单元测试（15个测试文件）
│   └── integration/        # 集成测试
├── tools/                  # CLI工具（11个工具脚本）
├── assets/                 # 知识库资源
├── configs/                # 配置文件
└── docs/                   # 项目文档
```

### 1.3 依赖关系分析

```
trae_test ──────────────────────────┐
    │                               │
    ├── core/db_pool.py            │
    ├── core/cache_manager.py      │──► PostgreSQL, Redis
    ├── orchestrator/agent_orchestrator.py
    ├── utils/test_case_generator.py
    ├── utils/knowledge_retriever.py ───► assets/knowledge_base/
    └── utils/test_case_strategy.py

auto_test ──────────────────────────┐
    │                               │
    ├── core/environment.py         │
    ├── core/test_data_factory.py   │──► 外部数据文件
    ├── core/test_data_lifecycle.py │
    ├── pages/*.py                  │──► Playwright
    ├── api/*.py                    │──► requests
    └── facades/*.py                │──► pages/ + api/
```

### 1.4 现有测试覆盖率

| 测试类型 | 位置 | 数量 | 特点 |
|---------|------|------|------|
| 单元测试 | `tests/unit/` | 15个文件 | 无浏览器依赖，执行快 |
| 集成测试 | `tests/integration/` | 1个文件 | 模块间协作测试 |
| UI测试 | `modules/auto_test/tests/` | 11个文件 | 依赖Playwright，执行慢 |
| E2E测试 | `tests/test_e2e_workflow.py` | 1个文件 | 完整业务流程 |

### 1.5 潜在瓶颈与改进点

| 类别 | 问题描述 | 严重程度 | 建议措施 |
|------|---------|---------|---------|
| **CI/CD缺失** | 无自动化构建/测试/部署流程 | **高** | 建立GitHub Actions流水线 |
| **测试执行效率** | UI测试串行执行，耗时较长 | 中 | 并行测试执行、测试分片 |
| **安全扫描** | 无代码安全漏洞扫描 | **高** | 集成bandit安全扫描 |
| **依赖管理** | 无依赖漏洞检测 | 中 | 集成safety/dependabot |
| **报告集成** | 测试报告手动生成 | 低 | CI中自动生成并上传报告 |
| **环境隔离** | 测试环境配置分散 | 中 | 统一环境配置管理 |
| **通知机制** | 无构建/测试失败通知 | 低 | 配置Slack/邮件通知 |
| **部署自动化** | 无自动化部署流程 | 中 | 配置环境部署流水线 |

---

## 二、CI/CD流程设计方案

### 2.1 设计原则

1. **最小代码改动**: 利用现有工具和配置，减少代码修改
2. **分层执行**: 快速失败，先执行轻量检查，再执行重量级测试
3. **并行化**: 单元测试与代码检查并行，UI测试分片执行
4. **安全优先**: 代码提交前必须通过所有质量检查
5. **可追溯**: 完整的构建历史和测试报告存档

### 2.2 工具选型

| 类别 | 工具 | 版本 | 理由 |
|------|------|------|------|
| CI平台 | GitHub Actions | - | 与代码仓库无缝集成，免费额度充足 |
| 代码检查 | ruff | 0.3+ | 已配置，执行速度快 |
| 格式化检查 | black | 24.0+ | 已配置，强制执行代码风格 |
| 类型检查 | mypy | 1.9+ | 已配置，提升代码质量 |
| 安全扫描 | bandit | 1.7+ | Python安全漏洞扫描 |
| 依赖检查 | safety | 2.3+ | 依赖包漏洞检测 |
| 测试框架 | pytest | 8.0+ | 已配置，支持并行执行 |
| 测试报告 | Allure | 2.13+ | 已配置，可视化报告 |
| 覆盖率 | pytest-cov | 4.1+ | 已配置，代码覆盖率统计 |

### 2.3 流程架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub Actions CI/CD                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
│  │  代码提交    │───►│  PR合并触发  │───►│  定时触发    │              │
│  └─────────────┘    └─────────────┘    └─────────────┘              │
│           │                                                          │
│           ▼                                                          │
│  ┌───────────────────────────────────────────────┐                  │
│  │              Stage 1: 快速检查                 │                  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │                  │
│  │  │  Ruff    │ │  Black   │ │  Mypy    │       │                  │
│  │  │  代码检查 │ │  格式检查 │ │  类型检查 │       │                  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘       │                  │
│  └───────┴────────────┴────────────┴──────────────┘                  │
│           │                                                          │
│           ▼ (全部通过)                                                │
│  ┌───────────────────────────────────────────────┐                  │
│  │              Stage 2: 安全扫描                 │                  │
│  │  ┌──────────┐ ┌──────────┐                     │                  │
│  │  │  Bandit  │ │  Safety  │                     │                  │
│  │  │  安全扫描 │ │  依赖检查 │                     │                  │
│  │  └────┬─────┘ └────┬─────┘                     │                  │
│  └───────┴────────────┴────────────────────────────┘                  │
│           │                                                          │
│           ▼ (全部通过)                                                │
│  ┌───────────────────────────────────────────────┐                  │
│  │              Stage 3: 测试执行                 │                  │
│  │  ┌──────────────────┐  ┌──────────────────┐    │                  │
│  │  │   单元测试        │  │   集成测试        │    │                  │
│  │  │  (并行执行)       │  │  (串行执行)       │    │                  │
│  │  └───────┬──────────┘  └───────┬──────────┘    │                  │
│  │          │                     │                │                  │
│  │          ▼                     ▼                │                  │
│  │  ┌──────────────────────────────────────────┐  │                  │
│  │  │              UI测试 (分片并行)             │  │                  │
│  │  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐      │  │                  │
│  │  │  │ 片1│ │ 片2│ │ 片3│ │ 片4│ │ 片5│      │  │                  │
│  │  │  └────┘ └────┘ └────┘ └────┘ └────┘      │  │                  │
│  │  └──────────────────────────────────────────┘  │                  │
│  └─────────────────────────────────────────────────┘                  │
│           │                                                          │
│           ▼ (全部通过)                                                │
│  ┌───────────────────────────────────────────────┐                  │
│  │              Stage 4: 报告生成                 │                  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │                  │
│  │  │ Allure   │ │ Coverage │ │  Artifact │       │                  │
│  │  │ 报告生成 │ │ 覆盖率报告│ │  产物上传 │       │                  │
│  │  └──────────┘ └──────────┘ └──────────┘       │                  │
│  └───────────────────────────────────────────────┘                  │
│           │                                                          │
│           ▼                                                          │
│  ┌───────────────────────────────────────────────┐                  │
│  │              Stage 5: 部署 (可选)              │                  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐       │                  │
│  │  │  测试环境 │ │  UAT环境 │ │ 生产环境  │       │                  │
│  │  │  自动部署 │ │  手动批准│ │ 手动批准  │       │                  │
│  │  └──────────┘ └──────────┘ └──────────┘       │                  │
│  └───────────────────────────────────────────────┘                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.4 阶段详细设计

#### Stage 1: 快速检查（并行执行）

| 任务 | 工具 | 命令 | 超时时间 |
|------|------|------|---------|
| 代码检查 | ruff | `ruff check .` | 5分钟 |
| 格式检查 | black | `black --check .` | 5分钟 |
| 类型检查 | mypy | `mypy .` | 10分钟 |

**触发条件**: 任意代码提交

**失败策略**: 快速失败，阻止后续阶段执行

#### Stage 2: 安全扫描（并行执行）

| 任务 | 工具 | 命令 | 超时时间 |
|------|------|------|---------|
| 安全扫描 | bandit | `bandit -r modules/ -f json -o bandit-report.json` | 10分钟 |
| 依赖检查 | safety | `safety check --json > safety-report.json` | 5分钟 |

**触发条件**: Stage 1 全部通过

**失败策略**: 发现高危漏洞时阻止后续阶段

#### Stage 3: 测试执行（分层执行）

| 测试类型 | 位置 | 命令 | 超时时间 | 并行度 |
|---------|------|------|---------|--------|
| 单元测试 | `tests/unit/` | `pytest tests/unit/ -v --tb=short -n auto` | 15分钟 | 4 |
| 集成测试 | `tests/integration/` | `pytest tests/integration/ -v --tb=short` | 30分钟 | 1 |
| UI测试 | `modules/auto_test/tests/` | `pytest modules/auto_test/tests/ -v --tb=short -n 5` | 60分钟 | 5 |

**触发条件**: Stage 2 全部通过

**失败策略**: 单元测试失败立即终止，集成/UI测试失败标记但继续

#### Stage 4: 报告生成

| 任务 | 工具 | 命令 | 超时时间 |
|------|------|------|---------|
| Allure报告 | allure-pytest | `allure generate reports/allure-results -o reports/allure-report` | 10分钟 |
| 覆盖率报告 | pytest-cov | 已在pytest中配置 | 包含在测试阶段 |
| 产物上传 | GitHub Actions | `actions/upload-artifact` | 5分钟 |

**触发条件**: Stage 3 完成

#### Stage 5: 部署（可选）

| 环境 | 部署方式 | 审批要求 |
|------|---------|---------|
| 测试环境 | 自动部署 | 无需审批 |
| UAT环境 | 手动部署 | 需要人工批准 |
| 生产环境 | 手动部署 | 需要人工批准 |

**触发条件**: Stage 4 完成且测试全部通过

---

## 三、实施步骤

### 3.1 Step 1: 创建 GitHub Actions 工作流文件

**文件路径**: `.github/workflows/ci-cd.yml`

**核心配置**:
- 触发条件: `push` 到 main 分支、`pull_request` 到 main 分支、定时触发（每日凌晨）
- 环境: Ubuntu 最新版
- Python版本: 3.12
- 缓存: pip依赖缓存

### 3.2 Step 2: 配置安全扫描工具

**文件路径**: `pyproject.toml`（追加配置）

**新增依赖**:
```toml
[project.optional-dependencies]
ci = [
    "bandit>=1.7.0",
    "safety>=2.3.0",
]
```

**Bandit配置**: `.bandit` 文件

### 3.3 Step 3: 配置测试分片（可选）

**目的**: 加速UI测试执行

**方案**: 使用 pytest-xdist 的 `--shard-id` 和 `--num-shards` 参数

### 3.4 Step 4: 配置环境变量

**GitHub Secrets**:
- `TEST_USERNAME`: 测试账号
- `TEST_PASSWORD`: 测试密码
- `TEST_WEB_BASE_URL`: 测试环境URL
- `TEST_WEB_API_BASE_URL`: 测试API URL

### 3.5 Step 5: 配置通知机制（可选）

**集成方式**:
- Slack通知: `act1ons/slack-notify`
- 邮件通知: `dawidd6/action-send-mail`

---

## 四、预期效益

| 维度 | 改进前 | 改进后 | 预期提升 |
|------|-------|-------|---------|
| **代码质量** | 手动检查 | 自动检查 | 100%代码质量保障 |
| **安全漏洞** | 无扫描 | 自动扫描 | 及时发现安全风险 |
| **测试执行** | 手动触发 | 自动触发 | 每次提交自动测试 |
| **执行效率** | 串行执行 | 并行执行 | 50%+时间节省 |
| **问题定位** | 手动排查 | 报告自动生成 | 快速定位问题 |
| **部署效率** | 手动部署 | 自动化部署 | 部署时间从小时级降至分钟级 |
| **团队协作** | 无流程规范 | 标准化流程 | 降低协作成本 |

---

## 五、风险评估及应对措施

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| **CI运行时间过长** | 高 | 中 | 并行执行、测试分片、缓存优化 |
| **依赖冲突** | 中 | 高 | 固定依赖版本、依赖锁定文件 |
| **测试环境不稳定** | 中 | 高 | 环境验证步骤、重试机制 |
| **安全扫描误报** | 中 | 低 | 配置扫描规则白名单 |
| **敏感信息泄露** | 低 | 高 | 使用GitHub Secrets、环境变量 |
| **部署失败** | 低 | 高 | 部署前验证、回滚机制 |
| **通知过载** | 中 | 低 | 仅发送失败通知、分组通知 |

---

## 六、最小代码改动清单

### 6.1 新增文件

| 文件路径 | 说明 | 大小 |
|---------|------|------|
| `.github/workflows/ci-cd.yml` | CI/CD工作流配置 | ~150行 |
| `.bandit` | Bandit安全扫描配置 | ~10行 |

### 6.2 修改文件

| 文件路径 | 修改内容 | 修改量 |
|---------|---------|--------|
| `pyproject.toml` | 追加CI依赖配置 | ~5行 |
| `pytest.ini` | 调整测试路径配置 | ~2行 |

### 6.3 配置变更

| 配置项 | 说明 |
|--------|------|
| GitHub Secrets | 添加测试环境变量 |
| GitHub Settings | 配置分支保护规则 |

---

## 七、实施计划

| 阶段 | 时间 | 负责人 | 交付物 |
|------|------|--------|--------|
| 阶段1: CI基础流程 | 第1天 | DevOps | `.github/workflows/ci-cd.yml` |
| 阶段2: 代码质量检查 | 第1天 | DevOps | ruff/black/mypy集成 |
| 阶段3: 安全扫描 | 第2天 | Security | bandit/safety集成 |
| 阶段4: 测试执行集成 | 第2天 | QA | pytest并行执行配置 |
| 阶段5: 报告生成 | 第3天 | DevOps | Allure报告上传 |
| 阶段6: 部署流程（可选） | 第3-5天 | DevOps | 环境部署流水线 |
| 阶段7: 通知与监控 | 第5天 | DevOps | 通知机制配置 |

---

## 八、附录

### 8.1 GitHub Actions 工作流模板

```yaml
name: Test ERP CI/CD

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 2 * * *'  # 每日凌晨2点

jobs:
  code-quality:
    name: 代码质量检查
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -e .[ci]
      - run: ruff check .
      - run: black --check .
      - run: mypy .

  security-scan:
    name: 安全扫描
    runs-on: ubuntu-latest
    needs: code-quality
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -e .[ci]
      - run: bandit -r modules/ -f json -o bandit-report.json
      - run: safety check --json > safety-report.json
      - uses: actions/upload-artifact@v4
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json

  unit-tests:
    name: 单元测试
    runs-on: ubuntu-latest
    needs: security-scan
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -e .
      - run: pytest tests/unit/ -v --tb=short -n auto
      - uses: actions/upload-artifact@v4
        with:
          name: unit-test-results
          path: reports/

  ui-tests:
    name: UI测试 (分片${{ matrix.shard }})
    runs-on: ubuntu-latest
    needs: unit-tests
    strategy:
      matrix:
        shard: [1, 2, 3, 4, 5]
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -e .
      - run: playwright install --with-deps chromium
      - run: |
          pytest modules/auto_test/tests/ -v --tb=short \
            --shard-id=${{ matrix.shard }} \
            --num-shards=5 \
            -p no:playwright
        env:
          TEST_USERNAME: ${{ secrets.TEST_USERNAME }}
          TEST_PASSWORD: ${{ secrets.TEST_PASSWORD }}
          TEST_WEB_BASE_URL: ${{ secrets.TEST_WEB_BASE_URL }}
          TEST_WEB_API_BASE_URL: ${{ secrets.TEST_WEB_API_BASE_URL }}

  report:
    name: 生成测试报告
    runs-on: ubuntu-latest
    needs: [unit-tests, ui-tests]
    if: always()
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: unit-test-results
          path: reports/
      - run: allure generate reports/allure-results -o reports/allure-report
      - uses: actions/upload-artifact@v4
        with:
          name: allure-report
          path: reports/allure-report/

  deploy-test:
    name: 部署到测试环境
    runs-on: ubuntu-latest
    needs: report
    if: success() && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: echo "部署到测试环境..."
```

### 8.2 Bandit 配置模板

```ini
[bandit]
exclude_dirs: .venv, tests, .git
tests: B101, B102, B103, B104, B105, B106, B107, B108, B109, B110
skips: []
```

### 8.3 分支保护规则建议

| 规则 | 配置 |
|------|------|
| 要求状态检查通过 | code-quality, security-scan, unit-tests |
| 需要拉取请求审查 | 至少1人批准 |
| 禁止强制推送 | 启用 |
| 禁止删除分支 | 启用 |

---

**文档结束**

> 本方案遵循"最小代码改动"原则，仅需新增2个配置文件和修改2个现有文件，即可建立完整的CI/CD流程。

> 待审核通过后，将立即执行代码修改工作。
