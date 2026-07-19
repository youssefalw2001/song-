from __future__ import annotations

import threading
import time

import pytest

from song_lab.rate_limit import ConcurrencyLimiter, RateLimitTimeoutError


class TestConcurrencyLimiter:
    def test_allows_up_to_max_concurrent_simultaneously(self):
        limiter = ConcurrencyLimiter(max_concurrent=2, wait_timeout_seconds=1.0)
        with limiter.acquire():
            with limiter.acquire():
                assert limiter.in_flight == 2

    def test_third_caller_times_out_when_at_capacity(self):
        limiter = ConcurrencyLimiter(max_concurrent=1, wait_timeout_seconds=0.05)
        with limiter.acquire():
            with pytest.raises(RateLimitTimeoutError):
                with limiter.acquire():
                    pass  # pragma: no cover - should never reach here

    def test_slot_is_released_after_context_exits(self):
        limiter = ConcurrencyLimiter(max_concurrent=1, wait_timeout_seconds=1.0)
        with limiter.acquire():
            pass
        assert limiter.in_flight == 0
        with limiter.acquire():
            assert limiter.in_flight == 1

    def test_slot_is_released_even_when_body_raises(self):
        limiter = ConcurrencyLimiter(max_concurrent=1, wait_timeout_seconds=1.0)
        with pytest.raises(ValueError):
            with limiter.acquire():
                raise ValueError("simulated failure inside the critical section")
        assert limiter.in_flight == 0
        with limiter.acquire():
            assert limiter.in_flight == 1

    def test_rejects_non_positive_max_concurrent(self):
        with pytest.raises(ValueError):
            ConcurrencyLimiter(max_concurrent=0)

    def test_a_freed_slot_unblocks_a_waiting_caller(self):
        limiter = ConcurrencyLimiter(max_concurrent=1, wait_timeout_seconds=2.0)
        results: list[str] = []

        def hold_then_release() -> None:
            with limiter.acquire():
                time.sleep(0.1)
            results.append("released")

        holder = threading.Thread(target=hold_then_release)
        holder.start()
        time.sleep(0.02)  # let the holder acquire first

        with limiter.acquire():
            results.append("waiter_acquired")

        holder.join()
        assert "released" in results
        assert "waiter_acquired" in results
