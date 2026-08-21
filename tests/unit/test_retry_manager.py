"""RetryManager 单元测试"""

import pytest

from modules.trae_test.orchestrator.config import RetryConfig
from modules.trae_test.orchestrator.retry_manager import RetryContext, RetryManager, with_retry


class TestRetryContext:
    def test_init(self):
        ctx = RetryContext()
        assert ctx.attempt == 0
        assert ctx.total_retries == 0

    def test_add_attempt(self):
        ctx = RetryContext()
        ctx.add_attempt()
        assert ctx.attempt == 1
        assert ctx.total_retries == 1

    def test_add_attempt_with_exception(self):
        ctx = RetryContext()
        ctx.add_attempt(Exception("test"))
        assert ctx.last_exception is not None
        assert len(ctx.history) == 1

    def test_get_execution_time(self):
        ctx = RetryContext()
        assert ctx.get_execution_time() == 0.0


class TestRetryManager:
    def test_init(self):
        mgr = RetryManager()
        assert mgr.config is not None
        assert mgr.context is not None

    def test_init_with_config(self):
        config = RetryConfig(max_retries=5)
        mgr = RetryManager(config=config)
        assert mgr.config.max_retries == 5

    def test_execute_with_retry_success(self):
        mgr = RetryManager()

        def success_func():
            return "success"

        result = mgr.execute_with_retry(success_func)
        assert result == "success"

    def test_execute_with_retry_failure(self):
        mgr = RetryManager()

        def fail_func():
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            mgr.execute_with_retry(fail_func)

    def test_execute_with_retry_disabled(self):
        config = RetryConfig(enabled=False)
        mgr = RetryManager(config=config)

        def fail_func():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            mgr.execute_with_retry(fail_func)

    def test_should_retry_on_exception_retryable(self):
        mgr = RetryManager()
        assert mgr.should_retry_on_exception(ConnectionError("conn")) is True
        assert mgr.should_retry_on_exception(TimeoutError("timeout")) is True

    def test_should_retry_on_exception_non_retryable(self):
        mgr = RetryManager()
        assert mgr.should_retry_on_exception(SyntaxError("syntax")) is False
        assert mgr.should_retry_on_exception(ValueError("value")) is False

    def test_should_retry_on_exception_by_message(self):
        mgr = RetryManager()
        assert mgr.should_retry_on_exception(Exception("timeout error")) is True
        assert mgr.should_retry_on_exception(Exception("permission denied")) is False

    def test_get_retry_summary(self):
        mgr = RetryManager()

        def success_func():
            return "ok"

        mgr.execute_with_retry(success_func)
        summary = mgr.get_retry_summary()
        assert summary["total_attempts"] > 0
        assert summary["successful"] is True

    def test_reset(self):
        mgr = RetryManager()
        mgr.context.attempt = 5
        mgr.reset()
        assert mgr.context.attempt == 0


class TestRetryDecorator:
    def test_with_retry_decorator(self):
        @with_retry(max_retries=1)
        def success_func():
            return "decorated"

        result = success_func()
        assert result == "decorated"

    def test_with_retry_decorator_failure(self):
        @with_retry(max_retries=1)
        def fail_func():
            raise ValueError("decorated fail")

        with pytest.raises(ValueError):
            fail_func()
