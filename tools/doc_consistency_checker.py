"""Validate the cross-file contract between AGENTS.md and project practices."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CORE_DOCS = (
    "docs/TRAE_TEST_WORKFLOW.md",
    "docs/AUTO_TEST_WORKFLOW.md",
    "docs/LOCAL_KNOWLEDGE_BASE_GUIDE.md",
    "docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md",
    "docs/KNOWLEDGE_BASE_RETRIEVER.md",
    "docs/ARCHITECTURE.md",
    "docs/CODING_RULES.md",
    "docs/PROJECT_ARTIFACT_PLACEMENT.md",
    "docs/AGENT_RULES.md",
)

FRONTMATTER_REQUIRED_FIELDS = ("title", "purpose", "version", "updated", "authority")

REQUIRED_ROUTES = {
    "测试用例生成": "docs/TRAE_TEST_WORKFLOW.md",
    "自动化测试执行": "docs/AUTO_TEST_WORKFLOW.md",
    "知识库检索": "docs/KNOWLEDGE_BASE_RETRIEVER.md",
    "知识库更新": "docs/KNOWLEDGE_BASE_UPDATE_WORKFLOW.md",
    "文件与产物管理": "docs/PROJECT_ARTIFACT_PLACEMENT.md",
    "代码审核": "docs/AGENT_RULES.md",
    "文档维护": "tools/doc_consistency_checker.py",
}

REMOVED_REFERENCES = (
    "tools/clean_workspace.py",
    ".trae/rules/agent_rules.md",
    ".trae/rules/coding_rules.md",
    ".trae/rules/project_rules.md",
)


class DocConsistencyChecker:
    """Check links, routes, entry points, stale references and frontmatter."""

    def __init__(self, project_root: Path | str | None = None):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1])
        self.issues: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []

    def _issue(self, rule: str, message: str, location: str = "") -> None:
        self.issues.append({"type": rule, "message": message, "location": location})

    def _warning(self, rule: str, message: str, location: str = "") -> None:
        self.warnings.append({"type": rule, "message": message, "location": location})

    def _read_agents(self) -> str:
        path = self.project_root / "AGENTS.md"
        if not path.exists():
            self._issue("missing_agents", "AGENTS.md 不存在", "AGENTS.md")
            return ""
        return path.read_text(encoding="utf-8")

    def check_route_closure(self, content: str) -> None:
        for route, target in REQUIRED_ROUTES.items():
            if route not in content:
                self._issue("missing_route", f"缺少任务路由：{route}", "AGENTS.md")
            if not (self.project_root / target).exists():
                self._issue("missing_route_target", f"路由目标不存在：{target}", target)

    def check_cross_file_links(self, content: str) -> None:
        for raw_link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            link = raw_link.split("#", 1)[0]
            if not link or link.startswith(("#", "http:", "https:")):
                continue
            if link.startswith(("assets/knowledge_base/", "workspace/")):
                continue
            if link.startswith(("docs/", "modules/", "tools/", "tests/")):
                if not (self.project_root / link).exists():
                    self._issue("missing_entry_point", f"入口不存在：{link}", link)

    def check_frontmatter(self) -> None:
        for relative_path in CORE_DOCS:
            path = self.project_root / relative_path
            if not path.exists():
                self._issue("missing_core_doc", f"核心文档不存在：{relative_path}", relative_path)
                continue
            content = path.read_text(encoding="utf-8").lstrip()
            if not content.startswith("---"):
                self._issue("missing_frontmatter", f"核心文档缺少 YAML frontmatter：{relative_path}", relative_path)
                continue
            lines = content.splitlines()
            try:
                end = lines[1:].index("---") + 1
            except ValueError:
                self._issue("invalid_frontmatter", f"YAML frontmatter 未闭合：{relative_path}", relative_path)
                continue
            fields = {
                line.split(":", 1)[0].strip()
                for line in lines[1:end]
                if ":" in line and not line.lstrip().startswith("#")
            }
            missing = [field for field in FRONTMATTER_REQUIRED_FIELDS if field not in fields]
            if missing:
                self._issue(
                    "incomplete_frontmatter",
                    f"frontmatter 缺少字段 {', '.join(missing)}：{relative_path}",
                    relative_path,
                )
            frontmatter_version = next(
                (
                    line.split(":", 1)[1].strip().lstrip("v")
                    for line in lines[1:end]
                    if line.strip().startswith("version:")
                ),
                "",
            )
            body_lines = lines[end + 1 :]
            metadata_lines = []
            for line in body_lines:
                if re.match(r"^#{1,6}\s", line):
                    break
                metadata_lines.append(line)
            body_version = re.search(
                r"版本[：:]\s*v?(\d+(?:\.\d+){1,2})",
                "\n".join(metadata_lines),
            )
            if body_version and frontmatter_version and body_version.group(1) != frontmatter_version:
                self._issue(
                    "version_mismatch",
                    f"frontmatter 版本 {frontmatter_version} 与正文版本 {body_version.group(1)} 不一致：{relative_path}",
                    relative_path,
                )

    def check_removed_references(self) -> None:
        candidates = [self.project_root / "AGENTS.md", *sorted((self.project_root / "docs").glob("*.md"))]
        for path in candidates:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            for reference in REMOVED_REFERENCES:
                if reference in content:
                    self._issue("removed_tool_reference", f"发现已删除入口引用：{reference}", str(path.relative_to(self.project_root)))

    def run(self) -> dict[str, object]:
        content = self._read_agents()
        self.check_route_closure(content)
        self.check_cross_file_links(content)
        self.check_frontmatter()
        self.check_removed_references()
        return {
            "passed": not self.issues,
            "issues": self.issues,
            "warnings": self.warnings,
            "exit_code": self.exit_code(),
        }

    def exit_code(self) -> int:
        if self.issues:
            return 2
        if self.warnings:
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 AGENTS.md 与专项文档、代码入口的一致性")
    parser.add_argument("--root", type=Path, default=None, help="项目根目录")
    parser.add_argument("--json", action="store_true", help="仅输出机器可读 JSON")
    args = parser.parse_args()
    result = DocConsistencyChecker(args.root).run()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"passed={result['passed']} issues={len(result['issues'])} warnings={len(result['warnings'])}")
        for issue in result["issues"]:
            print(f"ERROR {issue['type']}: {issue['message']} [{issue['location']}]")
        for warning in result["warnings"]:
            print(f"WARNING {warning['type']}: {warning['message']} [{warning['location']}]")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
