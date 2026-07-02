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

## What this creates

The `package` command creates a `test-package.json` containing:

- song analysis prompt
- Yemeni-style lyric adaptation prompt
- music generation prompt
- vocal direction prompt
- scoring rubric
- iteration checklist

The `mock-audio` command proves the audio pipeline shape works without needing a GPU model yet. It writes a mock generation JSON to `outputs/audio`.

## MVP target

Slow emotional Yemeni oud dream-pop cover.

The goal is to make one beautiful version first, then expand.

## Real model status

A real singing/music model is not bundled yet. The repo now has the provider structure needed to connect one next. The safest next production step is adding a local model adapter after we choose the exact generator we will run on your machine or GPU server.
