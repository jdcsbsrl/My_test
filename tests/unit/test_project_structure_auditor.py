from pathlib import Path
from types import SimpleNamespace

from tools.project_structure_auditor import ProjectStructureAuditor


def auditor_for(tmp_path: Path) -> ProjectStructureAuditor:
    auditor = ProjectStructureAuditor()
    auditor.PROJECT_ROOT = str(tmp_path)
    return auditor


def write_policy(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "PROJECT_ARTIFACT_PLACEMENT.md").write_text(
        "## 10. 根目录例外登记\n| 文件 | 所属工具 | 保留原因 | CI 使用 | 可迁移 |\n|---|---|---|---|---|\n| `allowed.json` | test | fixture | 否 | 是 |\n",
        encoding="utf-8",
    )


def test_registry_detects_unregistered_root_file(tmp_path):
    write_policy(tmp_path)
    (tmp_path / "allowed.json").write_text("{}", encoding="utf-8")
    (tmp_path / "foo.yaml").write_text("value: true", encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_root_artifacts_and_registry()

    assert any(issue["type"] == "unregistered_root_file" and issue["path"] == "foo.yaml" for issue in auditor.issues)
    assert not any(issue["path"] == "allowed.json" for issue in auditor.issues)


def test_root_artifact_detection_rejects_log_file(tmp_path):
    write_policy(tmp_path)
    (tmp_path / "debug.log").write_text("log", encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_root_artifacts_and_registry()

    assert any(issue["type"] == "root_artifact" for issue in auditor.issues)


def test_runtime_gitignore_check_allows_committed_keep_files(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text(
        ".runtime/**\n"
        "!.runtime/.keep\n"
        "workspace/**\n"
        "!workspace/.gitkeep\n"
        "data/private/*\n"
        "!data/private/.keep\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tools.project_structure_auditor.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=".runtime/.keep\nworkspace/.gitkeep\ndata/private/.keep\n"),
    )
    auditor = auditor_for(tmp_path)

    auditor._check_runtime_gitignore()

    assert not auditor.issues


def test_runtime_gitignore_rejects_nested_keep_exceptions(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text(
        ".runtime/**\n"
        "!.runtime/.keep\n"
        "!.runtime/**/\n"
        "!.runtime/**/.keep\n"
        "workspace/**\n"
        "!workspace/.gitkeep\n"
        "data/private/*\n"
        "!data/private/.keep\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tools.project_structure_auditor.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=".runtime/.keep\nworkspace/.gitkeep\ndata/private/.keep\n"),
    )
    auditor = auditor_for(tmp_path)

    auditor._check_runtime_gitignore()

    assert any(issue["type"] == "unsafe_runtime_gitignore_rule" for issue in auditor.issues)


def test_nonempty_unregistered_root_directory_is_blocking(tmp_path):
    extra = tmp_path / "downloads"
    extra.mkdir()
    (extra / "report.xlsx").write_text("artifact", encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_root_directories()

    assert any(issue["type"] == "unregistered_root_dir" and issue["path"] == "downloads" for issue in auditor.issues)


def test_empty_unregistered_root_directory_is_ignored(tmp_path):
    (tmp_path / "downloads").mkdir()
    auditor = auditor_for(tmp_path)

    auditor._check_root_directories()

    assert not auditor.issues


def test_bare_relative_write_path_is_warning(tmp_path):
    source = tmp_path / "tools"
    source.mkdir()
    (source / "writer.py").write_text('open("result.json", "w")\n', encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_bare_write_paths()

    assert auditor.warnings[0]["type"] == "bare_relative_write_path"


def test_empty_workspace_skeleton_does_not_warn(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitkeep").write_text("", encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_workspace_structure()

    assert not auditor.warnings


def test_required_dirs_reports_missing_assets(tmp_path):
    for required_dir in ProjectStructureAuditor.REQUIRED_DIRS:
        if required_dir != "assets":
            (tmp_path / required_dir).mkdir(parents=True)

    auditor = auditor_for(tmp_path)
    auditor._check_required_dirs()

    assert any(issue["type"] == "missing_required_dir" and issue["path"] == "assets" for issue in auditor.issues)


def test_required_dirs_passes_when_git_skeleton_is_present(tmp_path):
    for required_dir in ProjectStructureAuditor.REQUIRED_DIRS:
        (tmp_path / required_dir).mkdir(parents=True)

    auditor = auditor_for(tmp_path)
    auditor._check_required_dirs()

    assert not auditor.issues


def test_nonempty_workspace_without_date_dir_warns(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "unexpected.txt").write_text("artifact", encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_workspace_structure()

    assert any(warning["type"] == "no_date_dirs" for warning in auditor.warnings)


def test_exit_codes_distinguish_pass_warning_and_blocking(tmp_path):
    auditor = auditor_for(tmp_path)
    assert auditor.exit_code() == 0
    auditor.warnings.append({"type": "warning"})
    assert auditor.exit_code() == 1
    auditor.issues.append({"type": "issue"})
    assert auditor.exit_code() == 2
