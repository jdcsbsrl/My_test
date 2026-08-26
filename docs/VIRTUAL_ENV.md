---
title: Python 虚拟环境指南
purpose: Python 版本、虚拟环境创建、依赖同步和健康检查
version: 2.0.0
updated: 2026-08-26
authority: 专项规范
---

# Python 虚拟环境指南

**项目**: Test ERP Agent Workspace  
**更新时间**: 2026-08-26

---

## 基本信息

| 项目 | 说明 |
|------|------|
| 虚拟环境目录 | `.venv/` |
| 位置 | 项目根目录下的 `.venv/` |
| 规范版本 | Python 3.12（与 CI 一致） |
| 支持范围 | `pyproject.toml` 声明的 `>=3.12` |
| 状态判定 | 以本机健康检查结果为准，不在文档中硬编码 |

---

## 依赖管理文件

| 文件 | 位置 | 用途 |
|------|------|------|
| 依赖清单 | [requirements.txt](../requirements.txt) | 完整的Python依赖包列表 |
| 项目配置 | [pyproject.toml](../pyproject.toml) | 项目元数据和构建配置 |
| Git忽略 | [.gitignore](../.gitignore) | 虚拟环境已加入忽略规则 |

---

## 虚拟环境激活方式

### Windows PowerShell

```powershell
# 进入项目根目录
cd <project-root>

# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 验证
python --version
```

### Windows Command Prompt (CMD)

```cmd
# 进入项目根目录
cd <project-root>

# 激活虚拟环境
.venv\Scripts\activate.bat

# 验证
python --version
```

---

## 虚拟环境使用路径

**重要：使用虚拟环境中的 Python 时，应从项目根目录调用：**

| 工具 | 路径 |
|------|------|
| Python解释器 | `.venv\Scripts\python.exe` |
| pip包管理 | `.venv\Scripts\python.exe -m pip` |

---

## 已安装的核心依赖

| 依赖包 | 用途 |
|--------|------|
| pytest | 测试框架 |
| playwright | 浏览器自动化 |
| requests | HTTP请求 |
| openpyxl | Excel文件处理 |
| pyyaml | YAML配置解析 |
| python-dotenv | 环境变量管理 |

---

## 创建或重建虚拟环境

虚拟环境损坏、Python 版本不一致或 `pip check` 失败时，应在确认无需保留旧环境后重建：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .
```

重建 `.venv/` 会覆盖本地环境，执行前必须获得用户明确授权。

## 验证虚拟环境可用

```powershell
# 使用虚拟环境Python执行简单测试
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -c "import pytest; import playwright; print('虚拟环境验证通过！')"
```

---

## 虚拟环境特性

- ✅ 独立于系统Python环境
- ✅ 依赖版本应与 `pyproject.toml` 和 `uv.lock` 保持一致
- ✅ 已配置Git忽略，不提交到版本库
- ✅ 位于项目根目录，便于查找
