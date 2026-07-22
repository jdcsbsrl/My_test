"""Exception handling framework for auto_test module."""

import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from modules.auto_test.core.logger import get_logger

logger = get_logger()


class ErrorCode(Enum):
    SUCCESS = 0
    UNKNOWN_ERROR = 1000
    ENVIRONMENT_ERROR = 1001
    CONFIG_ERROR = 1002
    AUTHENTICATION_ERROR = 1003
    NETWORK_ERROR = 1004
    TIMEOUT_ERROR = 1005
    VALIDATION_ERROR = 1006
    DATA_ERROR = 1007
    BROWSER_ERROR = 1008
    API_ERROR = 1009
    ASSERTION_ERROR = 1010


class TestFrameworkError(Exception):
    """Base exception class for all test framework errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.cause = cause
        self.context = context or {}
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "error_type": self.error_code.name,
            "message": str(self),
            "timestamp": self.timestamp.isoformat(),
            "cause": str(self.cause) if self.cause else None,
            "context": self.context,
        }


class EnvironmentError(TestFrameworkError):
    """Raised when there's an environment-related error."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.ENVIRONMENT_ERROR, cause, context)


class ConfigError(TestFrameworkError):
    """Raised when there's a configuration error."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.CONFIG_ERROR, cause, context)


class AuthenticationError(TestFrameworkError):
    """Raised when authentication fails."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.AUTHENTICATION_ERROR, cause, context)


class NetworkError(TestFrameworkError):
    """Raised when there's a network-related error."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.NETWORK_ERROR, cause, context)


class TimeoutError(TestFrameworkError):
    """Raised when a timeout occurs."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.TIMEOUT_ERROR, cause, context)


class ValidationError(TestFrameworkError):
    """Raised when validation fails."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.VALIDATION_ERROR, cause, context)


class DataError(TestFrameworkError):
    """Raised when there's a data-related error."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.DATA_ERROR, cause, context)


class BrowserError(TestFrameworkError):
    """Raised when there's a browser-related error."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.BROWSER_ERROR, cause, context)


class APIError(TestFrameworkError):
    """Raised when an API call fails."""

    def __init__(self, message: str, status_code: int = None, cause=None, context=None):
        super().__init__(message, ErrorCode.API_ERROR, cause, context)
        self.status_code = status_code


class AssertionError(TestFrameworkError):
    """Raised when an assertion fails."""

    def __init__(self, message: str, cause=None, context=None):
        super().__init__(message, ErrorCode.ASSERTION_ERROR, cause, context)


@dataclass
class ErrorContext:
    """Context information for error reporting."""

    test_name: str | None = None
    test_module: str | None = None
    environment: str | None = None
    browser: str | None = None
    url: str | None = None
    step: str | None = None
    screenshot_path: str | None = None
    additional_info: dict[str, Any] = None

    def __post_init__(self):
        if self.additional_info is None:
            self.additional_info = {}


class ErrorHandler:
    """Centralized error handling component."""

    def __init__(self):
        self._error_handlers: dict[ErrorCode, list[Callable]] = {}
        self._global_handlers: list[Callable] = []

    def register_handler(
        self,
        error_code: ErrorCode,
        handler: Callable[[TestFrameworkError], None],
    ) -> None:
        """Register a handler for a specific error code."""
        if error_code not in self._error_handlers:
            self._error_handlers[error_code] = []
        self._error_handlers[error_code].append(handler)

    def register_global_handler(self, handler: Callable[[TestFrameworkError], None]) -> None:
        """Register a handler that's called for all errors."""
        self._global_handlers.append(handler)

    def handle(self, error: TestFrameworkError) -> None:
        """Handle an error by invoking all registered handlers."""
        for handler in self._global_handlers:
            try:
                handler(error)
            except Exception as e:
                logger.error(f"Error in global handler: {e}")

        handlers = self._error_handlers.get(error.error_code, [])
        for handler in handlers:
            try:
                handler(error)
            except Exception as e:
                logger.error(f"Error in handler for {error.error_code}: {e}")

    def log_error(self, error: TestFrameworkError) -> None:
        """Log error details to the logger."""
        error_dict = error.to_dict()
        logger.error(
            f"TestFrameworkError: {error.error_code.name} ({error.error_code.value})",
            extra={"error_details": error_dict},
        )

    def format_error_message(self, error: TestFrameworkError) -> str:
        """Format a detailed error message."""
        lines = [
            f"Error Code: {error.error_code.value} ({error.error_code.name})",
            f"Message: {error}",
            f"Timestamp: {error.timestamp}",
        ]
        if error.cause:
            lines.append(f"Cause: {error.cause}")
        if error.context:
            lines.append(f"Context: {error.context}")
        return "\n".join(lines)


def handle_errors(
    return_on_error: Any = None,
    expected_errors: list[type[Exception]] | None = None,
):
    """Decorator for handling errors in test functions.

    Args:
        return_on_error: Value to return if an error occurs
        expected_errors: List of exception types that should be caught
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except expected_errors or TestFrameworkError as e:
                error_handler = ErrorHandler()
                error_handler.log_error(e)
                error_handler.handle(e)
                return return_on_error
            except Exception as e:
                wrapped_error = TestFrameworkError(
                    message=str(e),
                    cause=e,
                    context={"function": func.__name__},
                )
                error_handler = ErrorHandler()
                error_handler.log_error(wrapped_error)
                error_handler.handle(wrapped_error)
                return return_on_error

        return wrapper

    return decorator


def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: list[type[Exception]] | None = None,
):
    """Decorator for retrying operations on error.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff_factor: Multiplier for exponential backoff
        retry_on: List of exception types that trigger retry
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_on or Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {current_delay:.2f} seconds..."
                        )
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed")

            raise last_exception

        return wrapper

    return decorator


def safe_execute(
    func: Callable,
    *args,
    error_message: str = "Operation failed",
    return_on_error: Any = None,
    **kwargs,
) -> Any:
    """Execute a function safely with error handling.

    Args:
        func: Function to execute
        error_message: Message to use if an error occurs
        return_on_error: Value to return if an error occurs

    Returns:
        The result of the function, or return_on_error if an error occurs
    """
    try:
        return func(*args, **kwargs)
    except TestFrameworkError as e:
        logger.error(f"{error_message}: {e}")
        return return_on_error
    except Exception as e:
        wrapped_error = TestFrameworkError(
            message=f"{error_message}: {e}",
            cause=e,
            context={"function": func.__name__},
        )
        error_handler = ErrorHandler()
        error_handler.log_error(wrapped_error)
        return return_on_error


class ErrorReporter:
    """Generates error reports for failed tests."""

    @staticmethod
    def generate_report(
        error: TestFrameworkError,
        context: ErrorContext | None = None,
    ) -> dict[str, Any]:
        """Generate a comprehensive error report."""
        report = {
            "error": error.to_dict(),
            "context": context.__dict__ if context else {},
            "system_info": {
                "python_version": sys.version,
                "timestamp": datetime.now().isoformat(),
            },
            "recommendations": ErrorReporter._generate_recommendations(error),
        }
        return report

    @staticmethod
    def _generate_recommendations(error: TestFrameworkError) -> list[str]:
        """Generate recommendations based on error type."""
        recommendations = []

        if error.error_code == ErrorCode.AUTHENTICATION_ERROR:
            recommendations.extend(
                [
                    "Check if credentials are correct",
                    "Verify if the account is locked",
                    "Ensure the authentication endpoint is reachable",
                ]
            )
        elif error.error_code == ErrorCode.NETWORK_ERROR:
            recommendations.extend(
                [
                    "Check network connectivity",
                    "Verify if the target server is running",
                    "Check firewall settings",
                ]
            )
        elif error.error_code == ErrorCode.TIMEOUT_ERROR:
            recommendations.extend(
                [
                    "Increase timeout settings",
                    "Check if the application is responding slowly",
                    "Consider reducing test scope",
                ]
            )
        elif error.error_code == ErrorCode.BROWSER_ERROR:
            recommendations.extend(
                [
                    "Ensure browser is properly installed",
                    "Check if browser version is compatible",
                    "Try using a different browser",
                ]
            )
        elif error.error_code == ErrorCode.API_ERROR:
            recommendations.extend(
                [
                    "Check API endpoint and method",
                    "Verify request parameters",
                    "Check API authentication",
                ]
            )

        return recommendations


_global_error_handler = ErrorHandler()


def get_error_handler() -> ErrorHandler:
    """Get the global error handler instance."""
    return _global_error_handler


def setup_default_error_handlers() -> None:
    """Setup default error handlers."""
    handler = get_error_handler()

    def log_handler(error: TestFrameworkError):
        handler.log_error(error)

    handler.register_global_handler(log_handler)
