# Yemeni Song Conversion Lab

Prototype for transforming English song ideas into Yemeni-inspired cover concepts.

## Current build

- Python CLI prototype
- Yemeni-inspired style presets
- Lyric adaptation prompt builder
- Music generation prompt builder
- Vocal direction prompt builder
- Version scoring rubric
- Mock audio provider for end-to-end flow testing
- ACE-Step REST API provider for real audio generation
- JSON output for repeatable testing

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m song_lab.cli package --input examples/master-of-none-vibe.txt --style yemeni_oud_dream_pop --output outputs/test-package.json
python -m song_lab.cli mock-audio --package outputs/test-package.json --output-dir outputs/audio
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m song_lab.cli package --input examples/master-of-none-vibe.txt --style yemeni_oud_dream_pop --output outputs/test-package.json
python -m song_lab.cli mock-audio --package outputs/test-package.json --output-dir outputs/audio
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
python -m song_lab.cli package --input examples/master-of-none-vibe.txt --style yemeni_oud_dream_pop --output outputs/test-package.json
python -m song_lab.cli ace-audio --package outputs/test-package.json --output-dir outputs/audio --base-url http://127.0.0.1:8001 --model acestep-v15-turbo --duration 90 --format mp3 --vocal-language ar
```

If generation succeeds, the final audio file will be saved under `outputs/audio`.

## What this creates

The `package` command creates a `test-package.json` containing:

- song analysis prompt
- Yemeni-style lyric adaptation prompt
- music generation prompt
- vocal direction prompt
- scoring rubric
- iteration checklist

The `mock-audio` command proves the audio pipeline shape works without needing a GPU model yet. It writes a mock generation JSON to `outputs/audio`.

The `ace-audio` command sends the package to a running ACE-Step API server, waits for completion, downloads the generated audio, and writes run metadata.

## MVP target

Slow emotional Yemeni oud dream-pop cover.

The goal is to make one beautiful version first, then expand.

## Real model status

The repo does not vendor ACE-Step model code or weights. It integrates with ACE-Step through its local REST API. That keeps this project small and lets ACE-Step handle GPU/model setup separately.
