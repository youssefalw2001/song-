"""Concurrency limiting for shared, rate-sensitive external resources.

The ACE-Step hosted completion API (acemusic.ai) is a free, unauthenticated-
by-default demo service with no published SLA or documented rate limit. If
this platform goes viral, an unbounded flood of concurrent generation
requests is the single fastest way to get throttled or blocked. This module
provides a simple, thread-safe cap on in-flight requests to that resource,
independent of how many worker threads/processes call into the provider.

Design notes:
- A bounded semaphore is the right primitive here (not a token-bucket rate
  limiter) because the constraint we care about is "how many requests are
  simultaneously in flight against a shared free service", not "how many
  requests per second" -- ACE-Step generations are long-running (seconds to
  minutes), so concurrency is the resource that matters.
- The limiter is process-local. It protects a single running instance of
  this backend from self-inflicted overload; it is not a substitute for a
  distributed rate limiter if this service is horizontally scaled across
  multiple processes/machines. That upgrade path is documented in the
  README when that scaling need actually arrives.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


class RateLimitTimeoutError(RuntimeError):
    """Raised when a caller waits longer than `wait_timeout_seconds` for a generation slot."""


@dataclass
class ConcurrencyLimiter:
    """Bounds the number of simultaneous in-flight calls to a shared resource.

    Args:
        max_concurrent: Hard ceiling on simultaneous acquisitions. Must be >= 1.
        wait_timeout_seconds: Maximum time a caller will block waiting for a
            free slot before `RateLimitTimeoutError` is raised. Prevents a
            traffic spike from queuing callers forever.
    """

    max_concurrent: int
    wait_timeout_seconds: float = 60.0
    _semaphore: threading.BoundedSemaphore = field(init=False, repr=False)
    _in_flight: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """Block (up to `wait_timeout_seconds`) until a generation slot is free, then hold it.

        Raises RateLimitTimeoutError if no slot becomes available in time.
        Always releases the slot on exit, including on exception, via the
        context manager protocol -- callers cannot leak a permanently held slot.
        """
        acquired = self._semaphore.acquire(timeout=self.wait_timeout_seconds)
        if not acquired:
            raise RateLimitTimeoutError(
                f"Timed out after {self.wait_timeout_seconds}s waiting for a free generation slot "
                f"(max_concurrent={self.max_concurrent}). The service is at capacity."
            )
        with self._lock:
            self._in_flight += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight -= 1
            self._semaphore.release()

    @property
    def in_flight(self) -> int:
        """Current number of callers holding a slot. For metrics/health checks only."""
        with self._lock:
            return self._in_flight
