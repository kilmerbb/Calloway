"""Retry and error handling utilities."""
import logging
import time
import functools
from typing import Callable, Type

logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    """All retry attempts failed."""
    def __init__(self, last_exception: Exception, attempts: int):
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts: {last_exception}")


def retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable | None = None,
):
    """Decorator for retry with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                        logger.warning(
                            f"{func.__name__} attempt {attempt}/{max_attempts} "
                            f"failed: {e}. Retrying in {delay:.1f}s"
                        )
                        if on_retry:
                            on_retry(attempt, e)
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
            raise RetryExhausted(last_exception, max_attempts)
        return wrapper
    return decorator


class CircuitBreaker:
    """Simple circuit breaker for external service calls."""

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time: float = 0
        self.state = "closed"  # closed, open, half_open

    def call(self, func: Callable, *args, **kwargs):
        if self.state == "open":
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.reset_timeout:
                self.state = "half_open"
                logger.info(f"Circuit breaker half-open, testing...")
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker open. Reset in {self.reset_timeout - elapsed:.0f}s"
                )

        try:
            result = func(*args, **kwargs)
            if self.state == "half_open":
                self.state = "closed"
                self.failures = 0
                logger.info("Circuit breaker closed (recovered)")
            return result
        except Exception as e:  # Broad catch: circuit breaker must track all failures
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    f"Circuit breaker opened after {self.failures} failures: {e}"
                )
            raise


class CircuitBreakerOpen(Exception):
    """Circuit breaker is open — service unavailable."""
    pass


def safe_execute(func: Callable, *args, default=None, log_error: bool = True, **kwargs):
    """Execute a function safely, returning default on any exception."""
    try:
        return func(*args, **kwargs)
    except Exception as e:  # Broad catch: safe_execute is designed to swallow all errors
        if log_error:
            logger.error(f"{func.__name__} failed: {e}")
        return default
