from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every retry/backoff path in the provider calls time.sleep -- collapse it to instant in tests.

    Autouse so no test accidentally takes real wall-clock time waiting on a
    simulated retry delay; tests that specifically want to assert sleep was
    called can still inspect the mock via monkeypatch.setattr's return value
    or a local override.
    """
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
