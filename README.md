# Yemeni Song Conversion Lab

Prototype for transforming English song ideas into Yemeni-inspired cover concepts.

## Current build

- Python CLI prototype
- Yemeni-inspired style presets
- Lyric adaptation prompt builder
- Music generation prompt builder
- Vocal direction prompt builder
- Version scoring rubric
- JSON output for repeatable testing

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m song_lab.cli --input examples/master-of-none-vibe.txt --style yemeni_oud_dream_pop --output outputs/test-package.json
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m song_lab.cli --input examples/master-of-none-vibe.txt --style yemeni_oud_dream_pop --output outputs/test-package.json
```

## What this creates

The CLI creates a `test-package.json` containing:

- song analysis prompt
- Yemeni-style lyric adaptation prompt
- music generation prompt
- vocal direction prompt
- scoring rubric
- iteration checklist

Paste the generated music prompt and lyric prompt into Suno, Udio, ACE-Step, or another generator to test the sound.

## MVP target

Slow emotional Yemeni oud dream-pop cover.

The goal is to make one beautiful version first, then expand.
