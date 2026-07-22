"""重试管理器 - 多Agent协同工作系统

提供可配置的重试机制，支持：
- 可配置重试次数
- 指数退避策略
- 重试日志记录
- 条件重试
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .config import RetryConfig

logger = logging.getLogger(__name__)


@dataclass
class RetryContext:
    """重试上下文"""

    # 当前尝试次数
    attempt: int = 0

    # 总重试次数
    total_retries: int = 0

    # 最后一次执行开始时间
    start_time: datetime | None = None

    # 最后一次执行结束时间
    end_time: datetime | None = None

    # 最后一次异常
    last_exception: Exception | None = None

    # 是否是最后一次尝试
    is_last_attempt: bool = False

    # 执行历史
    history: list = field(default_factory=list)

    def add_attempt(self, exception: Exception | None = None):
        """添加一次尝试记录"""
        self.attempt += 1
        self.total_retries += 1
        self.last_exception = exception
        self.start_time = datetime.now()

        record = {
            "attempt": self.attempt,
            "timestamp": self.start_time,
            "success": exception is None,
            "exception": str(exception) if exception else None,
        }
        self.history.append(record)

    def get_execution_time(self) -> float:
        """获取总执行时间（秒）"""
        if not self.start_time:
            return 0.0

        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()


class RetryManager:
    """重试管理器

    特性：
    - 可配置重试次数
    - 指数退避策略
    - 条件重试
    - 重试历史记录
    """

    def __init__(self, config: RetryConfig = None):
        """初始化重试管理器

        Args:
            config: 重试配置，如果为None则使用默认配置
        """
        self.config = config or RetryConfig()
        self.context = RetryContext()
        self._retry_count = 0

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        should_retry: Callable[[Exception], bool] | None = None,
        on_retry: Callable[[Exception, int], None] | None = None,
        **kwargs,
    ) -> Any:
        """使用重试机制执行函数

        Args:
            func: 要执行的函数
            *args: 函数位置参数
            should_retry: 判断是否应该重试的函数，接收异常参数
            on_retry: 重试时的回调函数，接收异常和尝试次数参数
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果

        Raises:
            Exception: 如果所有重试都失败，抛出最后一次异常
        """
        if not self.config.enabled:
            return func(*args, **kwargs)

        self.context = RetryContext()
        last_exception = None

        while self.context.attempt < self.config.max_retries + 1:
            self.context.attempt += 1
            self.context.total_retries += 1
            self.context.is_last_attempt = self.context.attempt == self.config.max_retries + 1

            try:
                self.context.start_time = datetime.now()
                result = func(*args, **kwargs)
                self.context.end_time = datetime.now()

                # 记录成功
                logger.info(
                    f"执行成功: 尝试 {self.context.attempt}/{self.config.max_retries + 1}, "
                    f"耗时 {self.context.get_execution_time():.2f}秒"
                )

                return result

            except Exception as e:
                last_exception = e
                self.context.last_exception = e
                self.context.end_time = datetime.now()

                # 记录失败
                logger.warning(
                    f"执行失败: 尝试 {self.context.attempt}/{self.config.max_retries + 1}, " f"错误: {str(e)}"
                )

                # 检查是否应该重试
                if self.context.is_last_attempt:
                    break

                if should_retry and not should_retry(e):
                    logger.info(f"判断不需要重试: {str(e)}")
                    break

                # 计算延迟
                delay = self.config.calculate_delay(self.context.attempt)

                # 记录重试
                if on_retry:
                    on_retry(e, self.context.attempt)

                logger.info(f"等待 {delay:.2f}秒后重试...")
                time.sleep(delay)

        # 所有重试都失败
        error_msg = f"重试 {self.config.max_retries} 次后仍然失败。\n" f"最后一次错误: {str(last_exception)}"
        logger.error(error_msg)
        raise last_exception

    def should_retry_on_exception(self, exception: Exception) -> bool:
        """判断是否应该重试特定的异常

        可以重试的异常：
        - 网络错误
        - 超时错误
        - 临时性错误

        不应该重试的异常：
        - 语法错误
        - 权限错误
        - 业务逻辑错误

        Args:
            exception: 异常对象

        Returns:
            bool: 是否应该重试
        """
        # 定义可以重试的异常类型
        retryable_exceptions = (
            ConnectionError,
            TimeoutError,
            FileNotFoundError,  # 文件可能稍后出现
            PermissionError,  # 权限可能稍后获取
        )

        # 定义不应该重试的异常类型
        non_retryable_exceptions = (
            SyntaxError,
            IndentationError,
            ImportError,  # 通常是配置问题
            ValueError,  # 通常是输入问题
            KeyError,  # 通常是数据问题
        )

        # 检查异常类型
        if isinstance(exception, non_retryable_exceptions):
            return False

        if isinstance(exception, retryable_exceptions):
            return True

        # 对于其他异常，检查错误消息
        error_msg = str(exception).lower()

        # 可以重试的关键字
        retry_keywords = ["timeout", "connection", "network", "temporarily", "unavailable", "busy"]

        # 不应该重试的关键字
        no_retry_keywords = ["invalid", "not found", "permission denied", "syntax error", "未找到", "权限", "语法错误"]

        for keyword in no_retry_keywords:
            if keyword.lower() in error_msg:
                return False

        for keyword in retry_keywords:
            if keyword.lower() in error_msg:
                return True

        # 默认不重试
        return False

    def get_retry_summary(self) -> dict:
        """获取重试摘要

        Returns:
            dict: 重试摘要信息
        """
        return {
            "total_attempts": self.context.total_retries,
            "successful": self.context.total_retries > 0 and self.context.last_exception is None,
            "final_exception": str(self.context.last_exception) if self.context.last_exception else None,
            "total_execution_time": self.context.get_execution_time(),
            "history": self.context.history,
        }

    def reset(self):
        """重置重试状态"""
        self.context = RetryContext()
        self._retry_count = 0


def with_retry(max_retries: int = 3, base_delay: float = 1.0, exponential_backoff: bool = True):
    """装饰器：为函数添加重试机制

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        exponential_backoff: 是否使用指数退避

    Returns:
        装饰后的函数

    Example:
        @with_retry(max_retries=3)
        def my_function():
            # 可能失败的代码
            pass
    """
    config = RetryConfig(max_retries=max_retries, base_delay=base_delay, exponential_backoff=exponential_backoff)

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            manager = RetryManager(config)
            return manager.execute_with_retry(func, *args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
