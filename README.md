# test_erp 测试管理平台

将 trae_test（测试用例生成）与 auto_test（自动化测试执行）合并的完整测试管理平台。

## 项目结构

```
test_erp/
├── pyproject.toml              # 项目配置和依赖
├── .env.example                # 环境变量示例
├── .gitignore
├── AGENTS.md                   # Agent 文档索引
├── README.md                   # 本文件
│
├── modules/                    # 模块目录
│   ├── trae_test/             # 测试用例生成模块
│   │   └── utils/             # 核心工具类
│   └── auto_test/             # 自动化测试执行模块
│       └── core/              # 核心功能
│
├── configs/                    # 配置文件
│   ├── test.yaml             # 测试环境配置
│   ├── uat.yaml              # UAT 环境配置
│   └── env_config.example.json
│
├── assets/                     # 资源文件
│   └── knowledge_base/        # 知识库
│
├── testcases/                  # 测试用例存储
│
├── tools/                      # 项目工具
│   ├── project_check.py       # 项目检查工具
│   └── case_generator_cli.py  # 用例生成命令行
│
├── docs/                       # 文档
│   └── ARCHITECTURE.md
│
└── .trae/                      # Trae 配置
    ├── agents/
    └── rules/
```

## 快速开始

### 1. 安装依赖

```bash
cd test_erp
pip install -e .
```

### 2. 配置环境

复制环境变量示例文件：

```bash
cp .env.example .env
```

编辑 `.env`，配置相关环境变量。

### 3. 项目检查

运行项目检查工具，验证环境是否正确：

```bash
python tools/project_check.py
```

### 4. 生成测试用例

```bash
# 查看可用模板
python tools/case_generator_cli.py list-templates

# 生成测试用例
python tools/case_generator_cli.py generate \
    --module 基础资料 \
    --function 物料新增 \
    --priority P1
```

## 模块说明

### trae_test 模块

负责测试用例的自动生成，包括：
- 测试场景分析
- 测试数据生成
- 测试用例模板管理
- 知识库驱动生成

### auto_test 模块

负责自动化测试执行，包括：
- 测试环境配置（多环境支持）
- 测试脚本执行
- 测试结果收集与分析
- 浏览器/API 测试支持

## 文档

- [AGENTS.md](AGENTS.md) - Agent 文档索引
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - 架构设计文档
- [configs/README.md](configs/README.md) - 配置文件说明

## 开发规范

参见 `.trae/rules/` 下的规则文档。
