import os

import pytest

import tools.clean_runtime as clean_runtime_module
from tools.clean_runtime import clean_runtime


def test_clean_runtime_respects_keep_file_and_age(tmp_path):
    runtime = tmp_path / ".runtime"
    reports = runtime / "reports"
    reports.mkdir(parents=True)
    old_file = reports / "old.log"
    kept_file = reports / "kept.log"
    old_file.write_text("old", encoding="utf-8")
    kept_file.write_text("kept", encoding="utf-8")
    (runtime / ".keep").write_text("reports/kept.log\n", encoding="utf-8")

    old_file.touch()
    old_file_time = old_file.stat().st_mtime - 15 * 86400
    os.utime(old_file, (old_file_time, old_file_time))

    removed = clean_runtime(keep_days=14, root=tmp_path)

    assert old_file in removed
    assert not old_file.exists()
    assert kept_file.exists()


def test_clean_runtime_respects_nested_keep_file(tmp_path):
    runtime = tmp_path / ".runtime"
    reports = runtime / "reports"
    reports.mkdir(parents=True)
    old_file = reports / "old.log"
    kept_file = reports / "kept.log"
    old_file.write_text("old", encoding="utf-8")
    kept_file.write_text("kept", encoding="utf-8")
    (reports / ".keep").write_text("*.log\n", encoding="utf-8")

    old_file_time = old_file.stat().st_mtime - 15 * 86400
    os.utime(old_file, (old_file_time, old_file_time))

    removed = clean_runtime(keep_days=14, root=tmp_path)

    assert removed == []
    assert old_file.exists()
    assert kept_file.exists()


def test_clean_runtime_rejects_path_traversal_in_keep_file(tmp_path):
    runtime = tmp_path / ".runtime"
    reports = runtime / "reports"
    reports.mkdir(parents=True)
    (runtime / ".keep").write_text("../outside.log\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid .keep pattern"):
        clean_runtime(keep_days=14, root=tmp_path)


def test_clean_runtime_dry_run_does_not_delete_old_file(tmp_path):
    runtime = tmp_path / ".runtime" / "cache"
    runtime.mkdir(parents=True)
    old_file = runtime / "old.tmp"
    old_file.write_text("old", encoding="utf-8")
    old_file_time = old_file.stat().st_mtime - 15 * 86400
    os.utime(old_file, (old_file_time, old_file_time))

    removed = clean_runtime(keep_days=14, root=tmp_path, dry_run=True)

    assert removed == [old_file]
    assert old_file.exists()


def test_clean_runtime_legacy_roots_are_opt_in_and_age_checked(tmp_path):
    legacy = tmp_path / ".runtime" / "pytest-old-run"
    legacy.mkdir(parents=True)
    old_file = legacy / "output.txt"
    old_file.write_text("old", encoding="utf-8")
    old_file_time = old_file.stat().st_mtime - 15 * 86400
    os.utime(old_file, (old_file_time, old_file_time))
    os.utime(legacy, (old_file_time, old_file_time))

    assert clean_runtime(keep_days=14, root=tmp_path) == []
    assert legacy.exists()

    removed = clean_runtime(keep_days=14, root=tmp_path, clean_legacy=True)

    assert removed == [legacy]
    assert not legacy.exists()


def test_clean_runtime_legacy_roots_keep_recent_directories(tmp_path):
    legacy = tmp_path / ".runtime" / "tmp-current"
    legacy.mkdir(parents=True)
    recent_file = legacy / "output.txt"
    recent_file.write_text("recent", encoding="utf-8")

    removed = clean_runtime(keep_days=14, root=tmp_path, clean_legacy=True)

    assert removed == []
    assert recent_file.exists()


def test_clean_runtime_legacy_dry_run_does_not_delete_root(tmp_path):
    legacy = tmp_path / ".runtime" / "cache-old"
    legacy.mkdir(parents=True)
    old_file = legacy / "cache.bin"
    old_file.write_bytes(b"old")
    import os

    old_file_time = old_file.stat().st_mtime - 15 * 86400
    os.utime(old_file, (old_file_time, old_file_time))
    os.utime(legacy, (old_file_time, old_file_time))

    removed = clean_runtime(keep_days=14, root=tmp_path, clean_legacy=True, dry_run=True)

    assert removed == [legacy]
    assert old_file.exists()


@pytest.mark.parametrize(
    "legacy_name",
    [
        "browser-temp-old-run",
        "validate-report-sync-old-run",
        "real-response-validation-old-run",
    ],
)
def test_clean_runtime_recognizes_all_legacy_root_families(tmp_path, legacy_name):
    runtime = tmp_path / ".runtime"
    legacy = runtime / legacy_name
    legacy.mkdir(parents=True)
    old_file = legacy / "output.txt"
    old_file.write_text("old", encoding="utf-8")

    old_file_time = old_file.stat().st_mtime - 15 * 86400
    os.utime(old_file, (old_file_time, old_file_time))
    os.utime(legacy, (old_file_time, old_file_time))

    removed = clean_runtime(keep_days=14, root=tmp_path, clean_legacy=True)

    assert removed == [legacy]
    assert not legacy.exists()


def test_clean_runtime_purge_legacy_roots_removes_recent_roots(tmp_path):
    runtime = tmp_path / ".runtime"
    legacy = runtime / "pytest-current-run"
    legacy.mkdir(parents=True)
    (legacy / "output.txt").write_text("recent", encoding="utf-8")

    removed = clean_runtime(keep_days=14, root=tmp_path, purge_legacy=True)

    assert removed == [legacy]
    assert not legacy.exists()


def test_clean_runtime_purge_does_not_remove_unrecognized_root(tmp_path):
    runtime = tmp_path / ".runtime"
    unknown = runtime / "keep-this-directory"
    unknown.mkdir(parents=True)
    (unknown / "output.txt").write_text("keep", encoding="utf-8")

    removed = clean_runtime(keep_days=0, root=tmp_path, purge_legacy=True)

    assert removed == []
    assert unknown.exists()


def test_clean_runtime_purge_skips_external_symlink(tmp_path):
    runtime = tmp_path / ".runtime"
    runtime.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_root = runtime / "pytest-linked-run"
    try:
        linked_root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境不允许创建目录链接")

    removed = clean_runtime(keep_days=0, root=tmp_path, purge_legacy=True)

    assert removed == []
    assert linked_root.is_symlink()
    assert outside.exists()


def test_clean_runtime_continues_after_legacy_root_removal_error(tmp_path, monkeypatch):
    runtime = tmp_path / ".runtime"
    blocked = runtime / "pytest-blocked-run"
    removable = runtime / "pytest-removable-run"
    blocked.mkdir(parents=True)
    removable.mkdir(parents=True)

    original_rmtree = clean_runtime_module.shutil.rmtree

    def rmtree_with_one_failure(path):
        if path == blocked:
            raise PermissionError("拒绝访问")
        original_rmtree(path)

    monkeypatch.setattr(clean_runtime_module.shutil, "rmtree", rmtree_with_one_failure)
    errors = []

    removed = clean_runtime(keep_days=0, root=tmp_path, clean_legacy=True, errors=errors)

    assert removed == [removable]
    assert not removable.exists()
    assert blocked.exists()
    assert errors and str(blocked) in errors[0]
