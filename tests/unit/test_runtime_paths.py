import subprocess
import sys
from pathlib import Path

import pytest

from modules.trae_test.utils.runtime_paths import runtime_dir


def test_runtime_dir_creates_named_runtime_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.trae_test.utils.runtime_paths.project_root",
        lambda: Path(tmp_path),
    )

    reports = runtime_dir("reports")

    assert reports == tmp_path / ".runtime" / "reports"
    assert reports.is_dir()


@pytest.mark.parametrize("kind", ["", "/tmp", "../outside", "reports/../../outside"])
def test_runtime_dir_rejects_unsafe_paths(kind):
    with pytest.raises(ValueError):
        runtime_dir(kind, create=False)


def test_runtime_paths_import_does_not_load_knowledge_base():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import modules.trae_test.utils.runtime_paths; "
            "assert 'modules.trae_test.utils.knowledge_retriever' not in sys.modules",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
