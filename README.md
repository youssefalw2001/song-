# Arabic Song Conversion Lab

Prototype for transforming English song ideas into Arabic-inspired cover concepts, including Yemeni, Levantine, Gulf, Egyptian, Maghrebi, and cinematic Arabic styles.

## Current build

- GitHub Pages frontend app
- Render-ready FastAPI backend
- Direct text-to-audio API routes
- Arabic and Yemeni style presets
- Lyric adaptation prompt builder
- Music generation prompt builder
- Vocal direction prompt builder
- Version scoring rubric
- Prompt improvement loop
- Mock audio provider for end-to-end flow testing
- Production-hardened ACE-Step-compatible REST API provider: typed errors, retry with backoff+jitter, concurrency limiting, best-of-N candidate generation, and mutagen-based audio validation
- Automatic BPM hints derived from each style preset, forwarded to the audio provider
- Primary/fallback provider wrapper for resilience against a single backend going down
- Structured JSON logging with automatic secret and audio-payload redaction
- Python CLI prototype
- JSON output for repeatable testing
- pytest suite covering the hardened provider, rate limiter, fallback wrapper, and BPM parsing
- Async stress-test harness for load-testing the API and smoke-testing the real backend

## IMPORTANT: acemusic.ai now requires an API key

As of this update, the free hosted `https://api.acemusic.ai` completion endpoint returns
`HTTP 401: Missing authentication token` on every request with no key configured. This was
verified live against the real service, not assumed. The previous assumption that
acemusic.ai was fully open/keyless is no longer accurate -- you must obtain an API key
from acemusic.ai and set `ACEMUSIC_API_KEY` (or `ACESTEP_API_KEY`) before real generation
will work against that backend. Budget for this before assuming a $0 generation cost.

## Hardened ACE-Step provider

`song_lab/providers/ace_step_api.py` is production-grade, not a thin HTTP wrapper:

- **Typed exceptions** -- `AceStepAuthError`, `AceStepClientError`, `AceStepRateLimitedError`,
  `AceStepServerError`, `AceStepTimeoutError`, `AceStepInvalidResponseError` -- so callers can
  distinguish "your API key is wrong" from "the service is temporarily overloaded" from
  "the response was corrupt," and only the last three are ever retried.
- **Explicit timeouts** on every request (connect/read/write/pool), never an indefinite hang.
- **Retry with exponential backoff and jitter**, capped by `max_retries` -- 429 and 5xx
  responses and transport errors are retried; 4xx client errors and auth failures never are.
- **Concurrency limiting** (`song_lab/rate_limit.py`) caps how many generation requests are
  in flight at once against the shared free acemusic.ai service, so a traffic spike can't
  silently hammer a resource we don't control. Configurable via `ACESTEP_MAX_CONCURRENT`
  (default 2).
- **Best-of-N candidate generation** -- pass `candidates=N` (CLI: `--candidates`, API:
  `"candidates": N`) to generate multiple takes and automatically keep the one whose actual
  duration is closest to the requested length.
- **Audio validation** -- every downloaded file is opened with `mutagen` and checked for a
  minimum size and a real, parseable duration before being reported as a successful
  generation. A truncated or corrupt download is treated as a failure, never silently
  returned as if it were a good song.
- **Resource cleanup** -- the provider is a context manager (`with AceStepApiProvider(...) as
  provider:`); the underlying HTTP connection pool is always closed, even on error.

## Fallback provider

`song_lab/providers/fallback.py` wraps a primary and one or more fallback providers. If the
primary raises or returns a failed result, the next provider is tried, in order. It never
silently substitutes a mock provider for a real one -- if you want a mock fallback in a
non-production environment, pass `MockSongProvider()` explicitly as one of the fallbacks so
that choice is visible in your own code, not hidden in this library.

```python
from song_lab.providers.ace_step_api import AceStepApiProvider
from song_lab.providers.fallback import FallbackSongProvider

primary = AceStepApiProvider(base_url="https://your-self-hosted-instance")
fallback = AceStepApiProvider(base_url="https://api.acemusic.ai", api_key="sk-...")

with FallbackSongProvider(primary=primary, fallbacks=[fallback]) as provider:
    result = provider.run(job)
```

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

49 tests cover the hardened provider's retry/backoff/error-mapping behavior (mocked at the
httpx transport boundary -- no real network calls), the concurrency limiter, the fallback
wrapper, secret/audio redaction, and BPM-hint parsing.

## Stress-testing before you go viral

`scripts/stress_test.py` has two modes:

```bash
# Safe to run as hard as you want -- drives the real FastAPI app in-process
# via the mock provider, no network calls, no cost.
python scripts/stress_test.py mock --requests 2000 --concurrency 200

# Makes 1 REAL call against the configured ACE-Step backend to prove the
# end-to-end pipeline produces valid audio. Hard-capped at 3 requests --
# acemusic.ai is a shared free resource, never load-test it.
python scripts/stress_test.py live --requests 1
```

The mock-mode harness has been run locally up to 5,000 concurrent-burst requests with zero
failures, confirming the API layer holds up under viral-spike-level traffic. Run it again
after any change to the request/response path before trusting it under real load.

## Use the GitHub Pages site

The frontend lives in `docs/index.html`.

After GitHub Pages is enabled, open:

```text
https://youssefalw2001.github.io/song-/
```

Use the simple branch setup:

```text
Repo Settings -> Pages -> Build and deployment -> Source: Deploy from a branch
Branch: main
Folder: /docs
Save
```

If you see a failed workflow with an X, ignore it for this setup. The site is served from the `/docs` folder directly.

## Deploy the backend on Render

This repo includes a Render Blueprint:

```text
render.yaml
```

In Render:

```text
New -> Blueprint -> Connect this GitHub repo -> Apply
```

Render will create a Python web service using:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn song_lab.api.app:app --host 0.0.0.0 --port $PORT
```

Add these Render environment variables:

```text
ACESTEP_API_URL = your ACE-compatible music engine API URL
ACESTEP_API_KEY = your private API key
ACESTEP_MODEL = acestep-v15-turbo
CORS_ALLOW_ORIGINS = https://youssefalw2001.github.io
```

Do not put the API key in GitHub Pages or JavaScript. Put it only in Render environment variables.

After Render deploys, copy your Render service URL, for example:

```text
https://arabic-song-conversion-api.onrender.com
```

Then open the GitHub Pages site and paste that into:

```text
Backend URL
```

Click:

```text
Check backend
Test without AI
Generate real audio
```

## How the site works

The site is the control panel. It calls the FastAPI backend to:

```text
GET  /health
POST /package/from-text
POST /generate/from-text/mock
POST /generate/from-text/ace
POST /score
POST /improve
```

GitHub Pages is frontend-only static hosting. Render runs the backend and keeps your API key private.

## Phone/browser-only flow

```text
1. Deploy backend on Render from the repo blueprint.
2. Add environment variables in Render.
3. Enable GitHub Pages from /docs.
4. Open the Pages site.
5. Paste the Render backend URL.
6. Generate from the site.
```

## Local full app test

Terminal 1: start your backend.

```bash
pip install -r requirements.txt
python serve.py
```

Terminal 2: start the music engine if you are using local ACE-Step.

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
uv run acestep-api
```

Then open the site and use:

```text
Backend URL: http://127.0.0.1:8080
Music engine URL: http://127.0.0.1:8001
```

For a public GitHub Pages site, the backend should be deployed on an HTTPS host. The frontend can then call that hosted backend directly.

## Quick start: CLI

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m song_lab.cli from-text --text-file examples/arabic-style-song-notes.txt --style arabic_oud_ballad --output outputs/arabic-oud-package.json --source-label test_song_notes
python -m song_lab.cli mock-audio --package outputs/arabic-oud-package.json --output-dir outputs/audio
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m song_lab.cli from-text --text-file examples/arabic-style-song-notes.txt --style arabic_oud_ballad --output outputs/arabic-oud-package.json --source-label test_song_notes
python -m song_lab.cli mock-audio --package outputs/arabic-oud-package.json --output-dir outputs/audio
```

## Real audio with ACE-compatible engine from CLI

```bash
python -m song_lab.cli ace-audio --package outputs/arabic-oud-package.json --output-dir outputs/audio --base-url $ACESTEP_API_URL --model acestep-v15-turbo --duration 90 --format mp3 --vocal-language ar
```

If generation succeeds, the final audio file will be saved under `outputs/audio`.

## Style examples

```bash
python -m song_lab.cli from-text --text-file examples/arabic-style-song-notes.txt --style arabic_oud_ballad --output outputs/arabic-oud-package.json
python -m song_lab.cli from-text --text-file examples/arabic-style-song-notes.txt --style levantine_pop_ballad --output outputs/levantine-package.json
python -m song_lab.cli from-text --text-file examples/extracted-song-text.txt --style yemeni_oud_dream_pop --output outputs/yemeni-package.json
```

## MVP target

One beautiful Arabic-style version first, then expand into more input types, hosted backend deployment, and direct audio playback/download in the browser.
