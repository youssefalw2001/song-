# Arabic Song Conversion Lab

Prototype for transforming English song ideas into Arabic-inspired cover concepts, including Yemeni, Levantine, Gulf, Egyptian, Maghrebi, and cinematic Arabic styles.

## Current build

- Python CLI prototype
- Arabic and Yemeni style presets
- Lyric adaptation prompt builder
- Music generation prompt builder
- Vocal direction prompt builder
- Version scoring rubric
- Prompt improvement loop
- Mock audio provider for end-to-end flow testing
- ACE-Step REST API provider for real audio generation
- FastAPI backend for app/front-end integration
- Text-file input flow for lyrics, notes, or song summaries
- JSON output for repeatable testing

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

## Quick start: API server

```bash
pip install -r requirements.txt
python serve.py
```

Then open:

```text
http://127.0.0.1:8080/docs
```

Useful endpoints:

```text
GET  /health
GET  /styles
POST /package/from-text
POST /generate/mock
POST /generate/ace
POST /score
POST /improve
```

## Real audio with ACE-Step

Run ACE-Step 1.5 as a separate local server first:

```bash
git clone https://github.com/ACE-Step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync
uv run acestep-api
```

Then, from this repo:

```bash
python -m song_lab.cli ace-audio --package outputs/arabic-oud-package.json --output-dir outputs/audio --base-url http://127.0.0.1:8001 --model acestep-v15-turbo --duration 90 --format mp3 --vocal-language ar
```

If generation succeeds, the final audio file will be saved under `outputs/audio`.

## Style examples

```bash
python -m song_lab.cli from-text --text-file examples/arabic-style-song-notes.txt --style arabic_oud_ballad --output outputs/arabic-oud-package.json
python -m song_lab.cli from-text --text-file examples/arabic-style-song-notes.txt --style levantine_pop_ballad --output outputs/levantine-package.json
python -m song_lab.cli from-text --text-file examples/extracted-song-text.txt --style yemeni_oud_dream_pop --output outputs/yemeni-package.json
```

## Iteration loop

```bash
python -m song_lab.cli score-version --artifact outputs/audio/example.mp3 --version-label v1 --emotion 8 --yemeni-identity 7 --vocal-beauty 7 --lyrics 7 --instrumental 7 --replay-value 7 --notes "Good first version. Improve chorus."
python -m song_lab.cli improve-prompt --package outputs/arabic-oud-package.json --scorebook outputs/scores.json --output outputs/improved-package.json
python -m song_lab.cli ace-audio --package outputs/improved-package.json --output-dir outputs/audio
```

## What this creates

The package commands create JSON containing:

- song analysis prompt
- Arabic-style lyric adaptation prompt
- music generation prompt
- vocal direction prompt
- scoring rubric
- iteration checklist

The `mock-audio` command proves the pipeline shape works without needing a GPU model yet.

The `ace-audio` command sends the package to a running ACE-Step API server, waits for completion, downloads the generated audio, and writes run metadata.

## MVP target

One beautiful Arabic-style version first, then expand into more input types, more styles, and a web UI.
