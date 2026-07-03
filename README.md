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
- ACE-Step-compatible REST API provider for real audio generation
- Python CLI prototype
- JSON output for repeatable testing

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
