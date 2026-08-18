"""项目结构审核工具 - 检查是否符合HarnessEngineer架构规范

审核项目结构：
1. 检查项目根目录是否有零散脚本
2. 检查输出文件位置是否正确
3. 检查模块结构是否完整
4. 验证是否符合规范
"""

import os
import sys
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
    ALLOWED_OUTPUT_DIRS = ["workspace"]

    # 禁止的输出目录
    FORBIDDEN_OUTPUT_DIRS = ["output", "test_cases_output", "modules/trae_test/output"]

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
        self._check_forbidden_scripts()
        self._check_output_dirs()
        self._check_module_structure()
        self._check_workspace_structure()
        self._generate_summary()

        return {
            "passed": len(self.issues) == 0,
            "issues": self.issues,
            "warnings": self.warnings,
            "timestamp": datetime.now().isoformat(),
        }

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
        else:
            self.warnings.append(
                {"type": "workspace_not_exists", "path": "workspace", "message": "workspace目录不存在，但已创建"}
            )
            print("  [WARN] workspace (不存在)")
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

        # 检查日期子目录
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
        else:
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
    auditor = ProjectStructureAuditor()
    result = auditor.audit()

    # 生成报告
    report_path = os.path.join(
        auditor.PROJECT_ROOT,
        "workspace",
        auditor.PROJECT_ROOT.split("\\")[-1],
        f"审核报告_项目结构_{datetime.now().strftime('%Y%m%d')}.txt",
    )

    # 确保workspace目录存在
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    auditor.generate_report(report_path)

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
