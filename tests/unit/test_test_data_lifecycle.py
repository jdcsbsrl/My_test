"""单元测试：test_data_lifecycle.py - 测试数据生命周期管理器

测试范围：
- 级联删除策略（拓扑排序）
- 兜底清理机制（API失败→DB直连）
- 清理失败日志记录
- 重试机制
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from modules.auto_test.core.test_data_lifecycle import TestDataLifecycleManager


class TestTopologicalSort:
    """测试拓扑排序功能（Kahn算法）"""

    def setup_method(self):
        self.manager = TestDataLifecycleManager(env="test")

    def test_simple_dependency(self):
        """测试简单依赖关系"""

        def dummy():
            pass

        self.manager.register_setup_task(dummy, task_name="create_order")
        self.manager.register_setup_task(
            dummy,
            task_name="create_delivery",
            dependencies=["create_order"],
        )
        self.manager.register_setup_task(
            dummy,
            task_name="create_invoice",
            dependencies=["create_delivery"],
        )

        result = self.manager._topological_sort()
        # 订单必须在发货前，发货必须在发票前
        assert result.index("create_order") < result.index("create_delivery")
        assert result.index("create_delivery") < result.index("create_invoice")

    def test_complex_dependency(self):
        """测试复杂依赖关系"""

        def dummy():
            pass

        self.manager.register_setup_task(dummy, task_name="task_a")
        self.manager.register_setup_task(dummy, task_name="task_b", dependencies=["task_a"])
        self.manager.register_setup_task(dummy, task_name="task_c", dependencies=["task_a"])
        self.manager.register_setup_task(dummy, task_name="task_d", dependencies=["task_b", "task_c"])

        result = self.manager._topological_sort()
        # A 必须在 B 和 C 之前
        assert result.index("task_a") < result.index("task_b")
        assert result.index("task_a") < result.index("task_c")
        # B 和 C 必须在 D 之前
        assert result.index("task_b") < result.index("task_d")
        assert result.index("task_c") < result.index("task_d")

    def test_no_dependencies(self):
        """测试无依赖关系"""

        def dummy():
            pass

        self.manager.register_setup_task(dummy, task_name="task_a")
        self.manager.register_setup_task(dummy, task_name="task_b")

        result = self.manager._topological_sort()
        assert len(result) == 2
        assert "task_a" in result
        assert "task_b" in result

    def test_circular_dependency(self):
        """测试循环依赖检测"""

        def dummy():
            pass

        self.manager.register_setup_task(dummy, task_name="task_a", dependencies=["task_b"])
        self.manager.register_setup_task(dummy, task_name="task_b", dependencies=["task_a"])

        with pytest.raises(ValueError, match="Circular dependency detected"):
            self.manager._topological_sort()

    def test_self_dependency(self):
        """测试自依赖检测"""

        def dummy():
            pass

        self.manager.register_setup_task(dummy, task_name="task_a", dependencies=["task_a"])

        with pytest.raises(ValueError, match="Circular dependency detected"):
            self.manager._topological_sort()


class TestCleanupMechanism:
    """测试清理机制"""

    def setup_method(self):
        self.manager = TestDataLifecycleManager(env="test")

    def test_successful_api_cleanup(self):
        """测试API清理成功"""
        mock_task = Mock(return_value=True)
        self.manager.register_cleanup_task(
            mock_task,
            fallback=Mock(),
        )

        self.manager.execute_cleanup()

        mock_task.assert_called_once()

    def test_api_failure_with_db_fallback(self):
        """测试API失败触发兜底清理"""
        mock_fallback = Mock(return_value=True)
        self.manager.register_cleanup_task(
            Mock(side_effect=Exception("API error")),
            fallback=mock_fallback,
        )

        self.manager.execute_cleanup()

        mock_fallback.assert_called_once()

    def test_both_api_and_db_fail(self):
        """测试API和兜底都失败"""
        self.manager.db_helper = MagicMock()
        mock_conn = MagicMock()
        self.manager.db_helper.connect.return_value = mock_conn

        self.manager.register_cleanup_task(
            Mock(side_effect=Exception("API error")),
            fallback=Mock(side_effect=Exception("DB error")),
        )

        # 不应抛出异常
        self.manager.execute_cleanup()

    def test_created_data_cleanup(self):
        """测试已创建数据的清理"""
        mock_cleanup = Mock(return_value=True)
        self.manager.register_created_data("order", "12345", mock_cleanup)

        self.manager.execute_cleanup()

        mock_cleanup.assert_called_once()

    def test_cleanup_order_reverse_creation(self):
        """测试清理顺序（后创建的先清理）"""
        cleanup_order = []

        def create_cleanup(name):
            def cleanup():
                cleanup_order.append(name)

            return cleanup

        self.manager.register_created_data("order", "1", create_cleanup("order1"))
        import time

        time.sleep(0.01)
        self.manager.register_created_data("order", "2", create_cleanup("order2"))

        self.manager.execute_cleanup()

        # order2 后创建，应先清理
        assert cleanup_order == ["order2", "order1"]

    def test_cleanup_failure_does_not_block(self):
        """测试单个清理失败不阻塞后续"""
        cleanup_log = []

        def cleanup_success():
            cleanup_log.append("success")

        self.manager.register_created_data("order", "fail", Mock(side_effect=Exception("cleanup error")))
        self.manager.register_created_data("order", "ok", cleanup_success)

        # 不应抛出异常
        self.manager.execute_cleanup()

        # 成功的清理仍应执行
        assert "success" in cleanup_log


class TestRetryMechanism:
    """测试重试机制"""

    def setup_method(self):
        self.manager = TestDataLifecycleManager(env="test")

    @patch("time.sleep", return_value=None)
    def test_retry_success_on_third_attempt(self, mock_sleep):
        """测试第三次重试成功"""
        call_count = [0]

        def flaky_task():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception(f"Attempt {call_count[0]} failed")
            return "success"

        result = self.manager._execute_with_retry(flaky_task)
        assert result == "success"
        assert call_count[0] == 3

    def test_retry_all_fail(self):
        """测试所有重试都失败"""
        call_count = [0]

        def always_fail():
            call_count[0] += 1
            raise Exception("Always fails")

        with pytest.raises(Exception, match="Always fails"):
            self.manager._execute_with_retry(always_fail)
        assert call_count[0] == 3  # 尝试了3次


class TestEnvironmentConfig:
    """测试环境配置"""

    def test_production_disables_db_fallback(self):
        """测试生产环境禁用DB兜底"""
        manager = TestDataLifecycleManager(env="production")
        assert manager._enable_db_fallback is False

    def test_test_enables_db_fallback(self):
        """测试环境启用DB兜底"""
        manager = TestDataLifecycleManager(env="test")
        assert manager._enable_db_fallback is True

    def test_staging_enables_db_fallback(self):
        """测试预生产环境启用DB兜底"""
        manager = TestDataLifecycleManager(env="staging")
        assert manager._enable_db_fallback is True

    def test_empty_setup_tasks(self):
        """测试无准备任务时不执行"""
        manager = TestDataLifecycleManager(env="test")
        # 不应抛出异常
        manager.execute_setup()

    def test_empty_cleanup_tasks(self):
        """测试无清理任务时不执行"""
        manager = TestDataLifecycleManager(env="test")
        # 不应抛出异常
        manager.execute_cleanup()
