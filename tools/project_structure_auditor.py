"""项目结构审核工具 - 检查是否符合HarnessEngineer架构规范

审核项目结构：
1. 检查项目根目录是否有零散脚本
2. 检查输出文件位置是否正确
3. 检查模块结构是否完整
4. 验证是否符合规范
"""

import os
import sys
import json
import argparse
import io
import fnmatch
import re
import subprocess
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path


class ProjectStructureAuditor:
    """项目结构审核器"""

    # 项目根目录
    PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

    # HarnessEngineer架构规范要求
    REQUIRED_DIRS = [
        "modules/trae_test",
        "modules/auto_test",
        "tools",
        "assets",
        "docs",
    ]
    ALLOWED_ROOT_DIRS = {
        ".git",
        ".github",
        ".runtime",
        ".venv",
        "assets",
        "browsers",
        "configs",
        "data",
        "docs",
        "evaluation",
        "fixtures",
        "modules",
        "tests",
        "tools",
        "workspace",
    }
    REQUIRED_GITIGNORE_RULES = (
        ".runtime/**",
        "!.runtime/.keep",
        "workspace/**",
        "!workspace/.gitkeep",
        "data/private/*",
        "!data/private/.keep",
    )
    FORBIDDEN_RUNTIME_GITIGNORE_RULES = (
        "!.runtime/**/",
        "!.runtime/**/.keep",
    )

    # 禁止在根目录的脚本模式
    FORBIDDEN_SCRIPTS_PATTERNS = [
        "generate_*.py",
        "run_*.py",
        "test_*.py",
        "manual_*.py",
        "audit_and_*.py",
        "copy_*.py",
    ]

    # 合法的输出目录（仅workspace）
    REGISTERED_ROOT_FILES = {
        "AGENTS.md",
        "README.md",
        "pyproject.toml",
        "pytest.ini",
        "requirements.txt",
        "uv.lock",
        ".bandit",
        ".gitattributes",
        ".gitignore",
        ".pre-commit-config.yaml",
        ".secrets.baseline",
        ".env",
        ".env.example",
    }
    ROOT_ARTIFACT_PATTERNS = [
        "*.log",
        "*.tmp",
        "*.bak",
        "*.zip",
        "*.xlsx",
        "*.xls",
        "*.csv",
        "*.json",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.html",
    ]
    WRITE_PATH_PATTERNS = [
        re.compile(r"\bopen\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wax+]"),
        re.compile(r"\bPath\(\s*['\"]([^'\"]+)['\"]\s*\)\.(?:write_text|write_bytes|touch)\b"),
        re.compile(r"\bos\.makedirs\(\s*['\"]([^'\"]+)['\"]"),
    ]

    # 禁止的输出目录
    FORBIDDEN_OUTPUT_DIRS = ["output", "test_cases_output", "modules/trae_test/output"]
    FORBIDDEN_WORKSPACE_SUBDIRS = {"formal", "draft", "test_cases", "exports"}

    # 合法的测试代码目录（不视为输出目录）
    ALLOWED_TEST_DIRS = ["testcases"]

    def __init__(self):
        self.audit_results = []
        self.issues = []
        self.warnings = []

    def audit(self) -> dict:
        """执行审核

        Returns:
            Dict: 审核结果
        """
        print("=" * 80)
        print("HarnessEngineer架构规范 - 项目结构审核")
        print("=" * 80)
        print()

        self._check_required_dirs()
        self._check_root_directories()
        self._check_forbidden_scripts()
        self._check_output_dirs()
        self._check_module_structure()
        self._check_workspace_structure()
        self._check_root_artifacts_and_registry()
        self._check_runtime_gitignore()
        self._check_bare_write_paths()
        self._generate_summary()

        return {
            "passed": len(self.issues) == 0,
            "issues": self.issues,
            "warnings": self.warnings,
            "timestamp": datetime.now().isoformat(),
        }

    def exit_code(self) -> int:
        """返回 CI 可用退出码：0 通过，1 警告，2 阻断。"""
        if self.issues:
            return 2
        return 1 if self.warnings else 0

    def _check_required_dirs(self):
        """检查必需的目录是否存在"""
        print("检查必需目录...")
        for dir_path in self.REQUIRED_DIRS:
            full_path = os.path.join(self.PROJECT_ROOT, dir_path)
            if os.path.exists(full_path):
                print(f"  [OK] {dir_path}")
            else:
                self.issues.append(
                    {"type": "missing_required_dir", "path": dir_path, "message": f"缺少必需的目录: {dir_path}"}
                )
                print(f"  [FAIL] {dir_path}")
        print()

    def _check_root_directories(self):
        """阻断包含内容的未登记顶层目录；空目录不进入 Git，允许本地暂存。"""
        print("检查顶层目录登记...")
        root = Path(self.PROJECT_ROOT)
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or path.name in self.ALLOWED_ROOT_DIRS:
                continue
            try:
                has_content = next(path.iterdir(), None) is not None
            except OSError as exc:
                self.warnings.append(
                    {
                        "type": "unreadable_root_dir",
                        "path": path.name,
                        "message": f"无法读取未登记顶层目录 {path.name}: {exc}",
                    }
                )
                continue
            if has_content:
                self.issues.append(
                    {
                        "type": "unregistered_root_dir",
                        "path": path.name,
                        "message": f"顶层目录未在项目规范登记: {path.name}",
                    }
                )
        print("  [OK] 顶层目录登记检查完成")
        print()

    def _check_forbidden_scripts(self):
        """检查根目录是否有禁止的脚本"""
        print("检查根目录禁止的脚本...")
        import fnmatch

        forbidden_scripts = []
        if os.path.exists(self.PROJECT_ROOT):
            for item in os.listdir(self.PROJECT_ROOT):
                item_path = os.path.join(self.PROJECT_ROOT, item)
                if os.path.isfile(item_path) and item.endswith(".py"):
                    for pattern in self.FORBIDDEN_SCRIPTS_PATTERNS:
                        if fnmatch.fnmatch(item, pattern):
                            forbidden_scripts.append(item)
                            break

        if forbidden_scripts:
            print(f"  [FAIL] 发现 {len(forbidden_scripts)} 个禁止的脚本:")
            for script in sorted(forbidden_scripts):
                self.issues.append(
                    {
                        "type": "forbidden_script",
                        "path": script,
                        "message": f"禁止在根目录存在脚本文件: {script}，应移动到tools/目录或相关模块",
                    }
                )
                print(f"     - {script}")
        else:
            print("  [OK] 根目录无禁止的脚本")
        print()

    def _check_output_dirs(self):
        """检查输出目录是否符合规范"""
        print("检查输出目录...")
        for dir_name in self.FORBIDDEN_OUTPUT_DIRS:
            dir_path = os.path.join(self.PROJECT_ROOT, dir_name)
            if os.path.exists(dir_path):
                files_count = len([f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))])
                self.issues.append(
                    {
                        "type": "forbidden_output_dir",
                        "path": dir_name,
                        "message": f"禁止的输出目录: {dir_name}，应统一使用workspace目录",
                    }
                )
                print(f"  [FAIL] {dir_name} ({files_count} 个文件)")

        # 检查workspace目录
        workspace_path = os.path.join(self.PROJECT_ROOT, "workspace")
        if os.path.exists(workspace_path):
            print("  [OK] workspace (正确的输出目录)")
        print()

    def _registered_root_files(self) -> set[str]:
        """读取规范文档中的根目录例外表。"""
        registered = set(self.REGISTERED_ROOT_FILES)
        doc_path = os.path.join(self.PROJECT_ROOT, "docs", "PROJECT_ARTIFACT_PLACEMENT.md")
        if not os.path.exists(doc_path):
            self.issues.append(
                {
                    "type": "missing_artifact_policy",
                    "path": "docs/PROJECT_ARTIFACT_PLACEMENT.md",
                    "message": "缺少项目文件与产物规范",
                }
            )
            return registered
        content = Path(doc_path).read_text(encoding="utf-8")
        marker = "## 10. 根目录例外登记"
        section = content.split(marker, 1)[1] if marker in content else ""
        table = re.findall(r"^\|\s*`([^`]+)`\s*\|", section, flags=re.MULTILINE)
        registered.update(table)
        return registered

    def _check_root_artifacts_and_registry(self):
        """检查根目录临时产物和未登记配置文件。"""
        print("检查根目录产物和例外登记...")
        registered = self._registered_root_files()
        for name in os.listdir(self.PROJECT_ROOT):
            path = os.path.join(self.PROJECT_ROOT, name)
            if not os.path.isfile(path) or name in registered:
                continue
            if any(fnmatch.fnmatch(name, pattern) for pattern in self.ROOT_ARTIFACT_PATTERNS):
                self.issues.append(
                    {"type": "root_artifact", "path": name, "message": f"根目录禁止放置运行产物: {name}"}
                )
            elif name.endswith((".json", ".yaml", ".yml", ".toml")) or name.startswith(("test_", "debug_", "temp_")):
                self.issues.append(
                    {
                        "type": "unregistered_root_file",
                        "path": name,
                        "message": f"根目录文件未在规范登记表中登记: {name}",
                    }
                )
        print("  [OK] 根目录产物和登记表检查完成")
        print()

    def _check_runtime_gitignore(self):
        """检查 .runtime、workspace 和私有数据是否被 Git 忽略。"""
        print("检查运行时和私有目录 Git 忽略规则...")
        gitignore = Path(self.PROJECT_ROOT) / ".gitignore"
        content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        for required in self.REQUIRED_GITIGNORE_RULES:
            if required not in content:
                self.issues.append(
                    {"type": "missing_gitignore_rule", "path": required, "message": f"缺少 Git 忽略规则: {required}"}
                )
        for forbidden in self.FORBIDDEN_RUNTIME_GITIGNORE_RULES:
            if forbidden in content:
                self.issues.append(
                    {
                        "type": "unsafe_runtime_gitignore_rule",
                        "path": forbidden,
                        "message": f"运行时忽略规则会重新暴露嵌套测试产物: {forbidden}",
                    }
                )
        tracked = subprocess.run(
            ["git", "ls-files", ".runtime", "workspace", "data/private"],
            cwd=self.PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        tracked_artifacts = [
            line for line in tracked.stdout.splitlines() if line and not Path(line).name.endswith((".keep", ".gitkeep"))
        ]
        if tracked_artifacts:
            self.issues.append(
                {
                    "type": "tracked_runtime_artifact",
                    "path": "\n".join(tracked_artifacts),
                    "message": "运行时、工作区或私有数据中存在被 Git 跟踪的文件",
                }
            )
        print("  [OK] Git 忽略规则检查完成")
        print()

    def _check_bare_write_paths(self):
        """扫描 Python 中写入项目根目录的裸相对路径，迁移期间先作为警告。"""
        print("检查裸相对路径写文件...")
        source_dirs = [
            Path(self.PROJECT_ROOT) / "modules",
            Path(self.PROJECT_ROOT) / "tools",
            Path(self.PROJECT_ROOT) / "fixtures",
        ]
        count = 0
        for source_dir in source_dirs:
            if not source_dir.exists():
                continue
            for source in source_dir.rglob("*.py"):
                try:
                    text = source.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for pattern in self.WRITE_PATH_PATTERNS:
                    for match in pattern.finditer(text):
                        value = match.group(1)
                        if (
                            not value.startswith((".runtime/", "workspace/", "/", "\\"))
                            and ".." not in Path(value).parts
                        ):
                            self.warnings.append(
                                {
                                    "type": "bare_relative_write_path",
                                    "path": str(source.relative_to(self.PROJECT_ROOT)),
                                    "message": f"发现裸相对路径写入: {value}",
                                }
                            )
                            count += 1
        print(f"  [WARN] 发现 {count} 个裸相对路径写入" if count else "  [OK] 未发现裸相对路径写入")
        print()

    def _check_module_structure(self):
        """检查模块结构"""
        print("检查模块结构...")

        # 检查trae_test模块
        trae_test_path = os.path.join(self.PROJECT_ROOT, "modules", "trae_test")
        if os.path.exists(trae_test_path):
            print("  [OK] modules/trae_test")

            # 检查utils目录
            utils_path = os.path.join(trae_test_path, "utils")
            if os.path.exists(utils_path):
                print("     [OK] utils/")
                required_utils = ["test_case_generator.py", "knowledge_retriever.py", "template_builder.py"]
                for util_file in required_utils:
                    util_path = os.path.join(utils_path, util_file)
                    if os.path.exists(util_path):
                        print(f"        [OK] {util_file}")
                    else:
                        self.warnings.append(
                            {
                                "type": "missing_utility",
                                "path": f"modules/trae_test/utils/{util_file}",
                                "message": f"建议的工具文件不存在: {util_file}",
                            }
                        )
                        print(f"        [WARN] {util_file}")
            else:
                self.issues.append(
                    {
                        "type": "missing_utils_dir",
                        "path": "modules/trae_test/utils",
                        "message": "trae_test模块缺少utils目录",
                    }
                )
                print("     [FAIL] utils/")

        # 检查auto_test模块
        auto_test_path = os.path.join(self.PROJECT_ROOT, "modules", "auto_test")
        if os.path.exists(auto_test_path):
            print("  [OK] modules/auto_test")

            # 检查必要的子目录
            required_auto_dirs = ["core", "api", "facades"]
            for sub_dir in required_auto_dirs:
                sub_path = os.path.join(auto_test_path, sub_dir)
                if os.path.exists(sub_path):
                    print(f"     [OK] {sub_dir}/")
                else:
                    self.warnings.append(
                        {
                            "type": "missing_sub_dir",
                            "path": f"modules/auto_test/{sub_dir}",
                            "message": f"auto_test模块缺少子目录: {sub_dir}",
                        }
                    )
                    print(f"     [WARN] {sub_dir}/")
        print()

    def _check_workspace_structure(self):
        """检查workspace目录结构"""
        print("检查workspace目录结构...")
        workspace_path = os.path.join(self.PROJECT_ROOT, "workspace")

        if not os.path.exists(workspace_path):
            self.warnings.append(
                {"type": "workspace_not_exists", "path": "workspace", "message": "workspace目录不存在"}
            )
            return

        # 检查日期子目录。CI 的全新 checkout 可能只有 .gitkeep，
        # 这种空骨架是合法状态，不应因为尚未产生交付物而报警。
        date_dirs = []
        for item in os.listdir(workspace_path):
            item_path = os.path.join(workspace_path, item)
            if os.path.isdir(item_path) and len(item) == 8 and item.isdigit():
                date_dirs.append(item)

        if date_dirs:
            print(f"  [OK] 找到 {len(date_dirs)} 个日期目录")
            for date_dir in sorted(date_dirs, reverse=True)[:5]:
                dir_path = os.path.join(workspace_path, date_dir)
                files_count = len([f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))])
                print(f"     [OK] {date_dir}/ ({files_count} 个文件)")
                for child in os.listdir(dir_path):
                    child_path = os.path.join(dir_path, child)
                    if os.path.isdir(child_path) and child in self.FORBIDDEN_WORKSPACE_SUBDIRS:
                        self.issues.append(
                            {
                                "type": "forbidden_workspace_subdir",
                                "path": os.path.relpath(child_path, self.PROJECT_ROOT),
                                "message": f"workspace日期目录下禁止创建 {child}/ 子目录",
                            }
                        )
        else:
            meaningful_entries = [item for item in os.listdir(workspace_path) if item not in {".gitkeep", ".keep"}]
            if not meaningful_entries:
                print("  [OK] workspace为空骨架，等待首个日期目录")
                print()
                return
            self.warnings.append(
                {"type": "no_date_dirs", "path": "workspace", "message": "workspace目录没有日期子目录"}
            )
            print("  [WARN] 没有日期子目录")
        print()

    def _generate_summary(self):
        """生成审核摘要"""
        print("=" * 80)
        print("审核摘要")
        print("=" * 80)
        print(f"审核时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"严重问题: {len(self.issues)} 个")
        print(f"警告: {len(self.warnings)} 个")
        print()

        if self.issues:
            print("严重问题列表:")
            for i, issue in enumerate(self.issues, start=1):
                print(f"  {i}. [{issue['type']}] {issue['message']}")
            print()

        if self.warnings:
            print("警告列表:")
            for i, warning in enumerate(self.warnings, start=1):
                print(f"  {i}. [{warning['type']}] {warning['message']}")
            print()

        if len(self.issues) == 0:
            print("[OK] 项目结构审核通过！")
        else:
            print("[FAIL] 项目结构审核未通过，请修复以上问题。")

        print("=" * 80)

    def generate_report(self, output_path: str = None):
        """生成审核报告

        Args:
            output_path: 输出文件路径
        """
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("HarnessEngineer架构规范 - 项目结构审核报告")
        report_lines.append("=" * 80)
        report_lines.append(f"审核时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"审核结果: {'通过' if len(self.issues) == 0 else '未通过'}")
        report_lines.append("")
        report_lines.append(f"严重问题: {len(self.issues)} 个")
        report_lines.append(f"警告: {len(self.warnings)} 个")
        report_lines.append("")

        if self.issues:
            report_lines.append("严重问题列表:")
            for i, issue in enumerate(self.issues, start=1):
                report_lines.append(f"  {i}. [{issue['type']}] {issue['message']}")
            report_lines.append("")

        if self.warnings:
            report_lines.append("警告列表:")
            for i, warning in enumerate(self.warnings, start=1):
                report_lines.append(f"  {i}. [{warning['type']}] {warning['message']}")
            report_lines.append("")

        report_lines.append("")
        report_lines.append("修正建议:")
        report_lines.append("  1. 将根目录的零散脚本移动到tools/目录")
        report_lines.append("  2. 将旧输出目录的文件迁移到workspace/{date}/目录")
        report_lines.append("  3. 删除output/、test_cases_output/等禁止的目录")
        report_lines.append("  4. 使用统一的Excel生成工具生成文件")
        report_lines.append("  5. 所有输出必须输出到workspace/{date}/目录")
        report_lines.append("")
        report_lines.append("=" * 80)

        report_text = "\n".join(report_lines)
        print(report_text)

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            print(f"\n报告已保存到: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="仅输出机器可读 JSON")
    args = parser.parse_args()
    auditor = ProjectStructureAuditor()
    if args.json:
        with redirect_stdout(io.StringIO()):
            result = auditor.audit()
    else:
        result = auditor.audit()

    if args.json:
        print(json.dumps({**result, "exit_code": auditor.exit_code()}, ensure_ascii=False))
    else:
        auditor.generate_report()
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "issues": len(result["issues"]),
                    "warnings": len(result["warnings"]),
                    "exit_code": auditor.exit_code(),
                },
                ensure_ascii=False,
            )
        )
    return auditor.exit_code()


if __name__ == "__main__":
    sys.exit(main())
