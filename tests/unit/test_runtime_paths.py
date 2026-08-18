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
