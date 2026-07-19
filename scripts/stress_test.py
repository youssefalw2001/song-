#!/usr/bin/env python3
"""Stress-test harness for the song generation API.

Two independent modes, because they test different things and carry very
different risk:

`mock` mode
    Drives the real FastAPI app in-process (no real network socket, via
    httpx's ASGITransport) through the full package-building pipeline and
    the mock audio provider, at real concurrency. This proves the API layer,
    request validation, and pipeline logic hold up under the kind of
    concurrent burst a viral clip would produce -- without spending a single
    call against the shared free acemusic.ai service or costing anything.

`live` mode
    Makes a small, tightly-capped number of REAL calls against the
    configured ACE-Step backend (acemusic.ai by default) through the
    hardened AceStepApiProvider, to prove the actual end-to-end pipeline
    produces valid, playable audio -- not just that the mock path works.
    This mode defaults to 1 request and hard-caps at 3 specifically because
    acemusic.ai is a free demo service with no published rate limit or SLA;
    this script must never be used to load-test a shared free resource we
    don't own.

Usage:
    python scripts/stress_test.py mock --requests 200 --concurrency 25
    python scripts/stress_test.py live --requests 1
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from song_lab.audio.jobs import SongJob  # noqa: E402
from song_lab.providers.ace_step_api import AceStepApiError, AceStepApiProvider  # noqa: E402

MAX_LIVE_REQUESTS = 3  # hard ceiling -- acemusic.ai is a shared free resource, not ours to hammer


@dataclass
class RequestOutcome:
    ok: bool
    status_code: int | None
    latency_seconds: float
    error: str | None = None


@dataclass
class LoadTestReport:
    outcomes: list[RequestOutcome] = field(default_factory=list)
    wall_clock_seconds: float = 0.0

    @property
    def success_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.ok)

    @property
    def failure_count(self) -> int:
        return len(self.outcomes) - self.success_count

    @property
    def latencies(self) -> list[float]:
        return [outcome.latency_seconds for outcome in self.outcomes]

    def percentile(self, pct: float) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        index = min(len(ordered) - 1, int(len(ordered) * pct))
        return ordered[index]

    def print_summary(self, label: str) -> None:
        total = len(self.outcomes)
        throughput = total / self.wall_clock_seconds if self.wall_clock_seconds > 0 else 0.0
        print(f"\n=== {label} ===")
        print(f"Total requests:      {total}")
        print(f"Succeeded:           {self.success_count}")
        print(f"Failed:              {self.failure_count}")
        print(f"Wall clock:          {self.wall_clock_seconds:.2f}s")
        print(f"Throughput:          {throughput:.2f} req/s")
        if self.latencies:
            print(f"Latency mean:        {statistics.mean(self.latencies):.3f}s")
            print(f"Latency p50:         {self.percentile(0.50):.3f}s")
            print(f"Latency p95:         {self.percentile(0.95):.3f}s")
            print(f"Latency p99:         {self.percentile(0.99):.3f}s")
            print(f"Latency max:         {max(self.latencies):.3f}s")
        if self.failure_count:
            sample_errors = [o.error for o in self.outcomes if not o.ok][:5]
            print(f"Sample errors:       {sample_errors}")


async def _run_mock_request(client: httpx.AsyncClient, index: int, output_dir: Path) -> RequestOutcome:
    payload = {
        "text": f"Stress test song idea number {index}: hype anthem, confident, chest-out energy.",
        "style": "hype_motivation_anthem",
        "source_label": f"stress_test_{index}",
        "lyrics": "",
        "output_dir": str(output_dir),
        "duration": 30,
    }
    started = time.perf_counter()
    try:
        response = await client.post("/generate/from-text/mock", json=payload, timeout=30.0)
        elapsed = time.perf_counter() - started
        ok = response.status_code == 200 and response.json().get("generation", {}).get("status") == "mock_generated"
        return RequestOutcome(ok=ok, status_code=response.status_code, latency_seconds=elapsed, error=None if ok else response.text[:200])
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return RequestOutcome(ok=False, status_code=None, latency_seconds=elapsed, error=f"{type(exc).__name__}: {exc}")


async def run_mock_load_test(total_requests: int, concurrency: int, output_dir: Path) -> LoadTestReport:
    from song_lab.api.app import app  # imported lazily so --help doesn't require the full app graph

    transport = httpx.ASGITransport(app=app)
    semaphore = asyncio.Semaphore(concurrency)
    report = LoadTestReport()

    async def bounded_request(client: httpx.AsyncClient, index: int) -> RequestOutcome:
        async with semaphore:
            return await _run_mock_request(client, index, output_dir)

    started = time.perf_counter()
    async with httpx.AsyncClient(transport=transport, base_url="http://stress-test.local") as client:
        tasks = [bounded_request(client, index) for index in range(total_requests)]
        report.outcomes = await asyncio.gather(*tasks)
    report.wall_clock_seconds = time.perf_counter() - started
    return report


def run_live_smoke_test(total_requests: int, output_dir: Path) -> LoadTestReport:
    """Makes real, sequential calls against the configured ACE-Step backend.

    Sequential, not concurrent -- this is a correctness smoke test of the
    real pipeline, not a load test of someone else's free service.
    """
    capped_requests = min(total_requests, MAX_LIVE_REQUESTS)
    if capped_requests < total_requests:
        print(f"Requested {total_requests} live requests; capping at {MAX_LIVE_REQUESTS} to avoid hammering a shared free API.")

    report = LoadTestReport()
    started = time.perf_counter()
    with AceStepApiProvider(base_url="https://api.acemusic.ai", max_retries=2, timeout_seconds=180, max_concurrent_requests=1) as provider:
        for index in range(capped_requests):
            job = SongJob(
                prompt="Confident hype motivation anthem, massive 808 bass, chant-rap hybrid delivery, chest-out energy, built for pre-game hype.",
                lyrics="[Verse 1]\nWoke up with a purpose, no time to hesitate\n\n[Hook]\nThis is my moment, I can feel it in my chest",
                output_dir=output_dir,
                duration_seconds=30,
                bpm_hint=75,
            )
            request_started = time.perf_counter()
            try:
                result = provider.run(job)
                elapsed = time.perf_counter() - request_started
                ok = result.status == "generated" and result.output_path.exists() and result.output_path.stat().st_size > 0
                report.outcomes.append(RequestOutcome(ok=ok, status_code=None, latency_seconds=elapsed, error=None if ok else result.message))
                if ok:
                    print(f"Live request {index + 1}/{capped_requests}: OK -> {result.output_path} ({result.output_path.stat().st_size} bytes, {elapsed:.1f}s)")
                else:
                    print(f"Live request {index + 1}/{capped_requests}: FAILED -> {result.message}")
            except AceStepApiError as exc:
                elapsed = time.perf_counter() - request_started
                report.outcomes.append(RequestOutcome(ok=False, status_code=None, latency_seconds=elapsed, error=str(exc)))
                print(f"Live request {index + 1}/{capped_requests}: EXCEPTION -> {type(exc).__name__}: {exc}")
    report.wall_clock_seconds = time.perf_counter() - started
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    mock_parser = subparsers.add_parser("mock", help="Concurrent load test against the in-process API using the mock provider.")
    mock_parser.add_argument("--requests", type=int, default=200, help="Total number of requests to send.")
    mock_parser.add_argument("--concurrency", type=int, default=25, help="Maximum number of requests in flight at once.")
    mock_parser.add_argument("--output-dir", type=Path, default=Path("outputs/stress_test_mock"), help="Directory for generated mock artifacts.")

    live_parser = subparsers.add_parser("live", help=f"Sequential smoke test against the real ACE-Step backend (capped at {MAX_LIVE_REQUESTS} requests).")
    live_parser.add_argument("--requests", type=int, default=1, help=f"Number of real requests to send (capped at {MAX_LIVE_REQUESTS}).")
    live_parser.add_argument("--output-dir", type=Path, default=Path("outputs/stress_test_live"), help="Directory for generated live audio artifacts.")

    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "mock":
        report = asyncio.run(run_mock_load_test(args.requests, args.concurrency, args.output_dir))
        report.print_summary(f"Mock load test ({args.requests} requests, concurrency={args.concurrency})")
    else:
        report = run_live_smoke_test(args.requests, args.output_dir)
        report.print_summary("Live smoke test against real ACE-Step backend")

    return 0 if report.failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
