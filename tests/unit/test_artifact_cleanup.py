import pytest

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
    import os

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

    import os

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
    import os

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
    import os

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
