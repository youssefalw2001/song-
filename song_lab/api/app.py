from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

from song_lab.api.schemas import AceGenerateRequest, GenerateRequest, ImproveRequest, ScoreRequest, TextPackageRequest
from song_lab.audio.jobs import SongJob
from song_lab.improve import improve_package
from song_lab.pipeline import build_conversion_package
from song_lab.presets import STYLE_PRESETS
from song_lab.providers.ace_step_api import AceStepApiProvider
from song_lab.providers.mock import MockSongProvider
from song_lab.scoring import VersionScore, append_score

app = FastAPI(title="Arabic Song Conversion Lab", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/styles")
def list_styles() -> dict:
    return {
        "styles": [
            {
                "key": key,
                "title": preset.title,
                "tempo_bpm": preset.tempo_bpm,
                "mood": preset.mood,
                "instruments": preset.instruments,
            }
            for key, preset in sorted(STYLE_PRESETS.items())
        ]
    }


@app.post("/package/from-text")
def package_from_text(request: TextPackageRequest) -> dict:
    if request.style not in STYLE_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown style: {request.style}")

    source_text = (
        f"Source label: {request.source_label}\n\n"
        "Treat this as extracted song material. Preserve the emotional meaning, not exact wording.\n\n"
        f"{request.text.strip()}"
    )
    package = build_conversion_package(source_text=source_text, style_key=request.style)
    data = package.model_dump()
    data["input_source"] = {"kind": "api_text", "source_label": request.source_label}
    return data


@app.post("/generate/mock")
def generate_mock(request: GenerateRequest) -> dict:
    package_data = _read_package(request.package_path)
    provider = MockSongProvider()
    result = provider.run(_job_from_package(package_data, request.output_dir, request.duration))
    return result.model_dump(mode="json")


@app.post("/generate/ace")
def generate_ace(request: AceGenerateRequest) -> dict:
    package_data = _read_package(request.package_path)
    provider = AceStepApiProvider(
        base_url=request.base_url,
        api_key=request.api_key,
        model=request.model,
        audio_format=request.audio_format,
        vocal_language=request.vocal_language,
    )
    result = provider.run(_job_from_package(package_data, request.output_dir, request.duration))
    return result.model_dump(mode="json")


@app.post("/score")
def score_version(request: ScoreRequest) -> dict:
    score = VersionScore(
        artifact_path=request.artifact,
        version_label=request.version_label,
        emotion=request.emotion,
        yemeni_identity=request.yemeni_identity,
        vocal_beauty=request.vocal_beauty,
        lyrics=request.lyrics,
        instrumental=request.instrumental,
        replay_value=request.replay_value,
        notes=request.notes,
    )
    scorebook = append_score(score, request.scorebook)
    return {"score": score.to_record(), "best": scorebook.get("best")}


@app.post("/improve")
def improve(request: ImproveRequest) -> dict:
    try:
        improved = improve_package(request.package_path, request.scorebook, request.output_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"output_path": str(request.output_path), "improvement_source": improved.get("improvement_source", {})}


def _read_package(package_path: Path) -> dict:
    if not package_path.exists():
        raise HTTPException(status_code=404, detail=f"Package not found: {package_path}")
    return json.loads(package_path.read_text(encoding="utf-8"))


def _job_from_package(package_data: dict, output_dir: Path, duration: int) -> SongJob:
    prompt = package_data.get("music_prompt", "").strip()
    lyrics = package_data.get("lyric_adaptation_prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Package is missing music_prompt")
    return SongJob(prompt=prompt, lyrics=lyrics, output_dir=output_dir, duration_seconds=duration)
