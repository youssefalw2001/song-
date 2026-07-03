from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from song_lab.api.schemas import AceGenerateRequest, GenerateRequest, ImproveRequest, ScoreRequest, TextAceGenerateRequest, TextPackageRequest
from song_lab.audio.jobs import SongJob
from song_lab.improve import improve_package
from song_lab.pipeline import build_conversion_package
from song_lab.presets import STYLE_PRESETS
from song_lab.providers.ace_step_api import AceStepApiProvider
from song_lab.providers.mock import MockSongProvider
from song_lab.scoring import VersionScore, append_score


def _allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="Arabic Song Conversion Lab", version="0.4.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    origin = request.headers.get("origin") or "*"
    allowed = _allowed_origins()
    response.headers["Access-Control-Allow-Origin"] = origin if "*" not in allowed else "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Vary"] = "Origin"
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "cors_allow_origins": _allowed_origins()}


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
    package = _package_from_text_request(request.text, request.style, request.source_label)
    data = package.model_dump()
    data["input_source"] = {"kind": "api_text", "source_label": request.source_label}
    return data


@app.post("/generate/from-text/mock")
def generate_from_text_mock(request: TextAceGenerateRequest) -> dict:
    package = _package_from_text_request(request.text, request.style, request.source_label)
    data = package.model_dump()
    if request.lyrics.strip():
        data["lyric_adaptation_prompt"] = request.lyrics.strip()
    provider = MockSongProvider()
    result = provider.run(_job_from_package(data, request.output_dir, request.duration))
    return {"package": data, "generation": result.model_dump(mode="json")}


@app.post("/generate/from-text/ace")
def generate_from_text_ace(request: TextAceGenerateRequest) -> dict:
    package = _package_from_text_request(request.text, request.style, request.source_label)
    data = package.model_dump()
    if request.lyrics.strip():
        data["lyric_adaptation_prompt"] = request.lyrics.strip()
    provider = AceStepApiProvider(
        base_url=request.base_url,
        api_key=request.api_key,
        model=request.model,
        audio_format=request.audio_format,
        vocal_language=request.vocal_language,
    )
    result = provider.run(_job_from_package(data, request.output_dir, request.duration))
    return {"package": data, "generation": result.model_dump(mode="json")}


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


def _package_from_text_request(text: str, style: str, source_label: str):
    if style not in STYLE_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown style: {style}")
    source_text = (
        f"Source label: {source_label}\n\n"
        "Treat this as extracted song material. Preserve the emotional meaning, not exact wording.\n\n"
        f"{text.strip()}"
    )
    return build_conversion_package(source_text=source_text, style_key=style)


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
