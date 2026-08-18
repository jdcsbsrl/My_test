from pathlib import Path

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
