"""Security boundary tests for test-data lifecycle and file/database access."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from modules.auto_test.core import db_helper as db_helper_module
from modules.auto_test.core.db_helper import DBHelper
from modules.auto_test.core.test_data_factory import DataLoader, DataValidationError, DataVersionManager
from modules.auto_test.core.test_data_lifecycle import (
    CleanupFailureError,
    CleanupOwnershipError,
    TestDataLifecycleManager as LifecycleManagerUnderTest,
)


def test_data_loader_rejects_nonexistent_path_outside_approved_root(tmp_path):
    loader = DataLoader(allowed_roots=[tmp_path / "allowed"])

    with pytest.raises(DataValidationError, match="outside the approved"):
        loader.load(tmp_path / "outside" / "missing.json")


def test_data_loader_rejects_symlink_resolved_outside_root(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = allowed / "link.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable in this test environment")

    with pytest.raises(DataValidationError, match="outside the approved"):
        DataLoader(allowed_roots=[allowed]).load(link)


def test_version_manager_rejects_traversal_and_external_version_symlink(tmp_path):
    data_dir = tmp_path / "versions"
    manager = DataVersionManager(data_dir=data_dir)

    with pytest.raises(DataValidationError):
        manager.save_version("..", {"unsafe": True}, "1.0")

    manager.save_version("orders", {"ok": True}, "1.0")
    outside = tmp_path / "orders_v9.0.json"
    outside.write_text('{"unsafe": true}', encoding="utf-8")
    link = data_dir / "orders_v9.0.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable in this test environment")

    with pytest.raises(DataValidationError, match="escaped"):
        manager.list_versions("orders")


def test_lifecycle_rejects_foreign_worker_and_tenant(monkeypatch):
    monkeypatch.setenv("TEST_RUN_ID", "run-a")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv("TEST_TENANT_ID", "tenant-a")
    manager = LifecycleManagerUnderTest(env="test")

    with pytest.raises(CleanupOwnershipError):
        manager.register_cleanup_task(
            Mock(),
            fallback=Mock(),
            data_type="order",
            data_id="order-1",
            owner_worker_id="gw1",
        )
    with pytest.raises(CleanupOwnershipError):
        manager.register_created_data(
            "order", "order-1", Mock(), owner_tenant_id="tenant-b"
        )


def test_db_fallback_is_tenant_scoped_and_releases_connection(monkeypatch):
    monkeypatch.setenv("TEST_RUN_ID", "run-a")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv("TEST_TENANT_ID", "tenant-a")
    manager = LifecycleManagerUnderTest(env="test")
    connection = MagicMock()
    connection.cursor.rowcount = 1
    manager.db_helper = MagicMock()
    manager.db_helper.connect.return_value = connection

    manager._db_fallback_cleanup(
        {
            "type": "order",
            "id": "order-1",
            "run_id": "run-a",
            "worker_id": "gw0",
            "tenant_id": "tenant-a",
        }
    )

    sql, params = connection.execute.call_args.args
    assert "tenant_id = %s" in sql
    assert params == ("order-1", "tenant-a")
    connection.close.assert_called_once()


def test_cleanup_failure_blocks_after_all_items_are_attempted(monkeypatch):
    manager = LifecycleManagerUnderTest(env="test")
    completed = []
    manager.register_created_data("order", "bad", Mock(side_effect=RuntimeError("bad")))
    manager.register_created_data("order", "good", lambda: completed.append("good"))
    manager.db_helper = MagicMock()
    fallback = MagicMock()
    fallback.execute.side_effect = RuntimeError("db unavailable")
    manager.db_helper.connect.return_value = fallback

    with pytest.raises(CleanupFailureError):
        manager.execute_cleanup()

    assert completed == ["good"]
    fallback.close.assert_called()


def test_db_helper_rejects_environment_mismatch_before_connect(monkeypatch):
    config = SimpleNamespace(
        env="test",
        get=lambda key, default=None: {"database.environment": "uat", "database.name": "test_db"}.get(
            key, default
        ),
    )
    monkeypatch.setattr(db_helper_module, "get_config", lambda env=None: config)

    helper = DBHelper(env="test")
    with pytest.raises(db_helper_module.EnvironmentSecurityError, match="binding mismatch"):
        helper.connect()
