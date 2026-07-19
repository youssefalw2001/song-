# Viral Song Lab

Platform for turning any idea -- a diss track on your friend, a birthday gift, a love
confession, a breakup anthem, a hype/motivation banger, sad lo-fi feels, or a country story
song -- into a catchy, shareable, real AI-generated song in English.

## Current build

- GitHub Pages frontend app
- Render-ready FastAPI backend
- Direct text-to-audio API routes
- English viral/occasion-first style presets (diss tracks, dancehall roasts, birthday
  anthems, love confessions, breakup anthems, hype anthems, sad lo-fi, country story songs)
- **Zero-external-LLM default (ACE-Step authors its own lyrics):** a prompt becomes a
  complete, unique song -- lyrics, hook, caption, and audio -- with no external LLM key
  required. Python does the deterministic occasion -> style -> brief structuring; ACE-Step's
  own built-in language model writes the actual lyrics via `sample_mode`. See "ACE-Step
  authors its own lyrics" below.
- Best-of-N autopilot planner (now fully optional/off-by-default): when `AUTOPILOT_API_KEY`
  is set, generates several distinct candidate lyric/hook concepts per request in one call
  and automatically selects the most specific, quotable, and safe one via a deterministic
  heuristic judge -- no second LLM call needed. See "Autopilot: best-of-N + judge" below.
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

**Never commit a real key or paste one into chat/logs.** Set it as an environment variable
(`export ACEMUSIC_API_KEY=...`) or in a git-ignored `.env` file only. Any key that has been
pasted into a chat, ticket, or log should be treated as compromised and rotated immediately.

## ACE-Step authors its own lyrics (default, zero external LLM)

The product default needs **no external LLM key at all**. A raw prompt becomes a complete,
one-of-a-kind song end to end using only the ACE-Step backend the platform already talks to:

1. **Python structures the request deterministically.** `build_song_brief()` in
   `song_lab/pipeline.py` is a pure function that fuses the user's idea, the chosen style
   preset's scaffold (tempo, instruments, mood, vocal direction), any optional per-song plan
   fields, and the safety guardrails into one natural-language brief. No network, no key,
   fully testable.
2. **ACE-Step's own built-in LM writes the lyrics and hook.** The brief is sent to the
   AceMusic completion API with `sample_mode: true`, so ACE-Step's internal language model
   authors the caption and lyrics itself, tailored to the prompt, then generates the audio in
   the same call. There is no second, external LLM in this path.
3. **The authored caption and lyrics are parsed back out** of the response and surfaced in the
   API response (`authored_caption`, `authored_lyrics` on `SongJobResult`) and in the
   frontend's "Show lyrics & details" panel -- these are the real words in the finished song.

Wiring:

- `SongJob.author_lyrics` (bool) + `SongJob.brief` (str) drive the behavior.
- `TextAceGenerateRequest.author_lyrics` defaults to `True`. If a user supplies their own
  `lyrics`, author mode is disabled automatically and the hand-written tagged path is used.
- The provider wraps the brief in a `<prompt>` tag and omits the `<lyrics>` tag; with
  `author_lyrics=False` the request is byte-for-byte identical to the previous behavior
  (backward compatible).

Verified live against `https://api.acemusic.ai`: a dancehall-roast brief produced a real
2.6 MB MP3 plus a structured `[Intro]/[Verse]/[Chorus]` lyric sheet and a style caption,
with no `AUTOPILOT_API_KEY` set. Note that ACE-Step's built-in LM is a small model and can
drift off the exact topic; the optional autopilot planner below can be layered on for tighter
lyrical control when a key is available.

## Autopilot: best-of-N + judge

`song_lab/autopilot.py` turns a raw user prompt into a full song plan (style, lyrics, hook,
caption). It is now **fully optional and off by default** -- the "ACE-Step authors its own
lyrics" path above is the zero-key default. Autopilot is only engaged when an API key is
configured, and it degrades gracefully to the offline template planner otherwise. There are
two paths:

- **No `AUTOPILOT_API_KEY`/`OPENAI_API_KEY` set:** uses the offline template planner
  (`_prompt_only_fallback`) -- fast, free, zero network calls, but the lyrics/hook are drawn
  from a fixed set of templates per style. Good for testing; not the "perfect and authentic"
  experience.
- **API key set:** requests `AUTOPILOT_CANDIDATE_COUNT` (default 3) genuinely different
  candidate concepts from the LLM in a single call, each with its own angle/hook/joke. Every
  candidate is scored by `song_lab/candidate_scoring.py` -- a pure, deterministic, offline
  heuristic judge that rewards specificity (does it actually use the names/details the user
  gave it, not generic filler?), penalizes known generic filler phrases, checks for a
  chantable hook repeated at least twice, and disqualifies anything that trips a narrow set
  of hard safety rules (self-harm incitement, explicit threats, leaked personal contact
  info) regardless of how well it scores otherwise. The highest-scoring eligible candidate
  is what actually reaches the user. If every candidate is disqualified or the LLM call
  fails for any reason (auth, rate limit, timeout, malformed response), the whole thing
  degrades to the offline template planner automatically -- a visitor never sees a hard
  error.

This is the standard "best-of-N + judge" pattern for lifting LLM output quality without a
second, slower/costlier LLM call to act as the judge. Configure it via:

```text
AUTOPILOT_API_KEY=sk-...            # or OPENAI_API_KEY
AUTOPILOT_API_URL=...                # optional, defaults to OpenAI chat completions
AUTOPILOT_MODEL=gpt-4.1-mini          # optional
AUTOPILOT_CANDIDATE_COUNT=3           # optional, how many candidates to generate per request
AUTOPILOT_MAX_RETRIES=2               # optional, retry attempts on transient failures
```

The safety disqualification list is intentionally narrow and is a defense-in-depth secondary
check, not the primary control -- the LLM system prompt is the primary safety instruction.
Production deployments handling arbitrary user content should also integrate a dedicated
moderation API for broader hate-speech/slur coverage.

### Verified live end-to-end

With a valid `ACEMUSIC_API_KEY` set, `python scripts/stress_test.py live --requests 1` was
run against the real backend and produced a genuine, valid song:

- Format: MP3, ID3v2.4, MPEG layer III
- Duration: 30.02s (requested 30s -- exact match)
- Bitrate: 128kbps, 48kHz, stereo
- Generation latency: ~32 seconds for a 30-second song
- File validated by `mutagen` as real, decodable audio (not a truncated/corrupt download)

This confirms the full pipeline -- prompt building, BPM hint forwarding, the hardened
provider's retry/timeout/validation logic, and real ACE-Step generation -- works end to end
against the production acemusic.ai backend, not just the mock path.

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
https://viral-song-lab-api.onrender.com
```

## Bake the backend URL into the frontend (one-time, permanent)

Visitors never see or configure a backend URL -- it's baked into the site once, by you, and
then it just works forever. Open `docs/index.html`, find this block near the top of the
`<script>` section, and set the URL once:

```js
const CONFIG = {
  BACKEND_URL: 'https://your-render-service.onrender.com' // <<< set this once
};
```

Commit and push. That's it -- every visitor's browser now talks to your backend automatically,
with zero setup, forever. If you ever move to a different Render service or your own
self-hosted backend, update this one line and push again.

A "Developer settings" panel is still available at the bottom of the page (collapsed by
default) with a backend override field, health check, and manual/mock generation tools --
useful for you when testing, invisible to a normal visitor.

## How the site works

The main experience is one screen, one button: type an idea (or tap an occasion card to
pre-fill one), hit "Make My Banger," and the backend handles lyrics, style, and real audio
generation automatically. No manual steps, no visible configuration.

Under the hood, the site calls the FastAPI backend at the URL baked into `CONFIG.BACKEND_URL`:

```text
GET  /health
POST /autopilot/plan
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
3. Bake the Render URL into CONFIG.BACKEND_URL in docs/index.html (one time).
4. Enable GitHub Pages from /docs.
5. Open the Pages site and just type an idea -- no setup needed.
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
python -m song_lab.cli from-text --text-file examples/hype-anthem-idea.txt --style hype_motivation_anthem --output outputs/hype-package.json --source-label test_song_notes
python -m song_lab.cli mock-audio --package outputs/hype-package.json --output-dir outputs/audio
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m song_lab.cli from-text --text-file examples/hype-anthem-idea.txt --style hype_motivation_anthem --output outputs/hype-package.json --source-label test_song_notes
python -m song_lab.cli mock-audio --package outputs/hype-package.json --output-dir outputs/audio
```

## Real audio with ACE-compatible engine from CLI

```bash
python -m song_lab.cli ace-audio --package outputs/hype-package.json --output-dir outputs/audio --base-url $ACESTEP_API_URL --model acestep-v15-turbo --duration 90 --format mp3 --vocal-language en
```

If generation succeeds, the final audio file will be saved under `outputs/audio`.

## Style examples

```bash
python -m song_lab.cli from-text --text-file examples/diss-track-idea.txt --style diss_track_trap --output outputs/diss-package.json
python -m song_lab.cli from-text --text-file examples/birthday-song-idea.txt --style birthday_banger_pop --output outputs/birthday-package.json
python -m song_lab.cli from-text --text-file examples/hype-anthem-idea.txt --style hype_motivation_anthem --output outputs/hype-package.json
```

## Available styles

| Style key | Occasion |
|---|---|
| `diss_track_trap` | Savage, comedic diss track to roast a friend |
| `dancehall_roast_anthem` | Playful dancehall-flavored roast/diss |
| `birthday_banger_pop` | Upbeat birthday gift anthem |
| `love_confession_rnb` | Sincere R&B love confession |
| `breakup_anthem_pop` | Cathartic-to-triumphant breakup anthem |
| `hype_motivation_anthem` | Chest-out hype/motivation banger |
| `sad_lofi_feels` | Late-night melancholic lo-fi |
| `country_story_love` | Warm, storytelling country song |

## MVP target

One certified-banger hype/diss-track version first, then expand into every occasion style,
hosted backend deployment, and direct audio playback/download in the browser.
