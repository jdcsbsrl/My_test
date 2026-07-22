# Python 虚拟环境指南

**项目**: Test ERP Agent Workspace  
**更新时间**: 2026-05-06

---

## 基本信息

| 项目 | 说明 |
|------|------|
| 虚拟环境目录 | `.venv/` |
| 位置 | `d:\Working\test_erp\.venv\` |
| Python版本 | 3.14.4 |
| 状态 | ✅ 已安装并可用 |

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
# 进入项目目录
cd d:\Working\test_erp

# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 验证
python --version
```

### Windows Command Prompt (CMD)

```cmd
# 进入项目目录
cd d:\Working\test_erp

# 激活虚拟环境
.venv\Scripts\activate.bat

# 验证
python --version
```

---

## 虚拟环境使用路径

**重要：使用虚拟环境中的Python时，请使用以下完整路径：**

| 工具 | 路径 |
|------|------|
| Python解释器 | `d:\Working\test_erp\.venv\Scripts\python.exe` |
| pip包管理 | `d:\Working\test_erp\.venv\Scripts\pip.exe` |

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

## 验证虚拟环境可用

```powershell
# 使用虚拟环境Python执行简单测试
d:\Working\test_erp\.venv\Scripts\python.exe -c "import pytest; import playwright; print('虚拟环境验证通过！')"
```

---

## 虚拟环境特性

- ✅ 独立于系统Python环境
- ✅ 包含所有项目所需依赖
- ✅ 已配置Git忽略，不提交到版本库
- ✅ 位于项目根目录，便于查找
