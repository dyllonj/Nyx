import threading
import time
from dataclasses import dataclass
from typing import Callable, TypeVar


Result = TypeVar("Result")


@dataclass
class CircuitBreakerOpenError(Exception):
    name: str
    retry_after_sec: float

    def __str__(self) -> str:
        return f"{self.name} circuit is open for another {self.retry_after_sec:.1f}s"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int,
        recovery_timeout_sec: float,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self._time_fn = time_fn or time.monotonic
        self._lock = threading.Lock()
        self._failure_count = 0
        self._opened_at: float | None = None

    def _retry_after_sec(self, now: float) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.recovery_timeout_sec - (now - self._opened_at))

    def call(self, fn: Callable[[], Result]) -> Result:
        now = self._time_fn()
        with self._lock:
            retry_after_sec = self._retry_after_sec(now)
            if retry_after_sec > 0:
                raise CircuitBreakerOpenError(self.name, retry_after_sec)
            if self._opened_at is not None:
                self._failure_count = 0
                self._opened_at = None

        try:
            result = fn()
        except Exception:
            with self._lock:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._opened_at = self._time_fn()
            raise

        with self._lock:
            self._failure_count = 0
            self._opened_at = None
        return result
