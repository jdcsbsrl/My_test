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
    (tmp_path / ".gitignore").write_text(".runtime/**\nworkspace/**\ndata/private/**\n", encoding="utf-8")
    monkeypatch.setattr(
        "tools.project_structure_auditor.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=".runtime/.keep\nworkspace/.gitkeep\ndata/private/.keep\n"),
    )
    auditor = auditor_for(tmp_path)

    auditor._check_runtime_gitignore()

    assert not auditor.issues


def test_bare_relative_write_path_is_warning(tmp_path):
    source = tmp_path / "tools"
    source.mkdir()
    (source / "writer.py").write_text('open("result.json", "w")\n', encoding="utf-8")
    auditor = auditor_for(tmp_path)

    auditor._check_bare_write_paths()

    assert auditor.warnings[0]["type"] == "bare_relative_write_path"


def test_exit_codes_distinguish_pass_warning_and_blocking(tmp_path):
    auditor = auditor_for(tmp_path)
    assert auditor.exit_code() == 0
    auditor.warnings.append({"type": "warning"})
    assert auditor.exit_code() == 1
    auditor.issues.append({"type": "issue"})
    assert auditor.exit_code() == 2
