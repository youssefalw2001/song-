from __future__ import annotations

import json
import os
import re
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from song_lab.api.schemas import AceGenerateRequest, GenerateRequest, ImproveRequest, LyricsGenerateRequest, ScoreRequest, TextAceGenerateRequest, TextPackageRequest
from song_lab.audio.jobs import SongJob, SongJobResult
from song_lab.autopilot import build_autopilot_plan
from song_lab.improve import improve_package
from song_lab.pipeline import build_conversion_package, build_song_brief
from song_lab.presets import STYLE_PRESETS
from song_lab.providers.ace_step_api import AceStepApiError, AceStepApiProvider
from song_lab.providers.mock import MockSongProvider
from song_lab.scoring import VersionScore, append_score
from song_lab.sound_options import (
    AESTHETICS,
    GENRES,
    LYRIC_STARTERS,
    TEMPOS,
    VIBES,
    VOCAL_STYLES,
    VOICES,
    compose_style,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_INDEX = ROOT_DIR / "docs" / "index.html"
OUTPUTS_DIR = ROOT_DIR / "outputs"
UPLOADS_DIR = OUTPUTS_DIR / "uploads"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

TREND_STYLE_DNA = {
    "dancehall_roast_wave": {"label": "Dancehall roast/diss viral pattern", "profile": "dancehall_roast_anthem", "score": 93, "dna": "bouncy dancehall riddim, playful savage lyrics, group sing-back hook, meme-able ad-lib tag, made to be sent to the person it's about", "safe_note": "Playful roast energy only, never real hate speech or harassment."},
    "trap_diss_punchline_wave": {"label": "Trap diss-track punchline pattern", "profile": "diss_track_trap", "score": 92, "dna": "half-time 808 trap beat, punchline-first bars, chantable hook, comedic-savage tone, built for group-chat sharing", "safe_note": "Comedic diss energy only, never real hate speech or harassment."},
    "birthday_singalong_wave": {"label": "Birthday singalong anthem pattern", "profile": "birthday_banger_pop", "score": 87, "dna": "bright four-on-the-floor pop, name said early and often, big group-chant chorus, confetti energy", "safe_note": "Use broad celebratory pop pattern only."},
    "love_confession_rnb_wave": {"label": "Sincere R&B love-confession pattern", "profile": "love_confession_rnb", "score": 85, "dna": "warm electric piano, intimate close-mic vocal, specific personal detail in the verse, soulful climb into the chorus", "safe_note": "Use broad sincere R&B pattern only."},
    "breakup_glow_up_wave": {"label": "Breakup glow-up anthem pattern", "profile": "breakup_anthem_pop", "score": 88, "dna": "raw verse into a defiant, empowered pop-rock chorus, bittersweet-to-triumphant arc, big singalong hook", "safe_note": "Use broad empowerment-arc pattern only."},
    "hype_lockin_wave": {"label": "Hype/motivation lock-in anthem pattern", "profile": "hype_motivation_anthem", "score": 90, "dna": "massive 808s, chant-rap hybrid delivery, riser into every hook, chest-out declarative lyrics", "safe_note": "Use broad hype-anthem pattern only."},
    "sad_lofi_2am_wave": {"label": "Sad lo-fi 2am diary pattern", "profile": "sad_lofi_feels", "score": 84, "dna": "dusty lo-fi drums, warm vinyl texture, intimate detached vocal, quietly devastating hook, negative space in the mix", "safe_note": "Use broad lo-fi mood/texture only."},
}

LIVE_TREND_URLS = [
    "https://ads.tiktok.com/business/creativecenter/inspiration/popular/music/mobile/en",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US",
]


def _allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="Viral Song Lab", version="0.8.0")
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

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


@app.get("/")
def home() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(FRONTEND_INDEX)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "cors_allow_origins": _allowed_origins(), "frontend": FRONTEND_INDEX.exists(), "outputs": OUTPUTS_DIR.exists(), "uploads": UPLOADS_DIR.exists(), "autopilot_api_configured": bool(os.getenv("AUTOPILOT_API_KEY") or os.getenv("OPENAI_API_KEY"))}


@app.get("/styles")
def list_styles() -> dict:
    return {"styles": [{"key": key, "title": preset.title, "tempo_bpm": preset.tempo_bpm, "mood": preset.mood, "instruments": preset.instruments} for key, preset in sorted(STYLE_PRESETS.items())]}


@app.post("/autopilot/plan")
def autopilot_plan(request: dict) -> dict:
    # build_autopilot_plan never raises for LLM-side failures -- it degrades to the
    # offline template planner internally (see song_lab/autopilot.py) so a visitor
    # never sees a hard error just because the LLM call had a bad moment. This
    # try/except only guards against genuinely malformed request payloads.
    try:
        return build_autopilot_plan(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/trends/live")
def live_trend_scan() -> dict:
    sources: list[dict] = []
    combined = ""
    for url in LIVE_TREND_URLS:
        item = {"url": url, "ok": False, "matches": []}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SongTrendScanner/1.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                text = response.read(200_000).decode("utf-8", errors="ignore")
            combined += "\n" + text.lower()
            item["ok"] = True
            item["matches"] = _extract_trend_terms(text)
        except Exception as exc:
            item["error"] = str(exc)[:160]
        sources.append(item)
    suggestion = _choose_trend_profile(combined)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "status": "live_scan_ok" if any(s.get("ok") for s in sources) else "fallback_patterns_only", "suggested_profile": suggestion["profile"], "suggested_pattern_key": suggestion["key"], "suggested_pattern": suggestion, "locked_style_dna": TREND_STYLE_DNA, "sources": sources, "originality_guardrail": "Create a fully original song. Do not copy melodies, lyrics, chord progressions, beats, riffs, arrangements, voices, or artist likenesses."}


def _extract_trend_terms(text: str) -> list[str]:
    lowered = re.sub(r"<[^>]+>", " ", text.lower())
    phrases = ["slowed", "speed up", "sped up", "edit", "nostalgia", "diss", "roast", "dancehall", "birthday", "breakup", "hype", "motivation", "lofi", "lo-fi", "r&b", "trap", "viral", "remix", "capcut"]
    found = []
    for phrase in phrases:
        if phrase in lowered and phrase not in found:
            found.append(phrase)
    titles = re.findall(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    for title in titles[:5]:
        cleaned = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", title)).strip()
        if cleaned and cleaned.lower() not in [x.lower() for x in found]:
            found.append(cleaned[:80])
    return found[:12]


def _choose_trend_profile(text: str) -> dict:
    scores: dict[str, int] = {key: int(value["score"]) for key, value in TREND_STYLE_DNA.items()}
    boosts = {
        "dancehall_roast_wave": ["dancehall", "roast", "diss", "jamaican", "reggae", "viral"],
        "trap_diss_punchline_wave": ["diss", "roast", "trap", "808", "punchline", "exposed"],
        "birthday_singalong_wave": ["birthday", "bday", "party", "celebrate"],
        "love_confession_rnb_wave": ["love", "crush", "r&b", "confession", "anniversary"],
        "breakup_glow_up_wave": ["breakup", "ex", "glow up", "moving on"],
        "hype_lockin_wave": ["hype", "motivation", "gym", "lock in", "pregame"],
        "sad_lofi_2am_wave": ["sad", "lofi", "lo-fi", "2am", "lonely"],
    }
    for key, words in boosts.items():
        for word in words:
            if word in text:
                scores[key] += 4
    best_key = max(scores, key=scores.get)
    best = dict(TREND_STYLE_DNA[best_key])
    best["key"] = best_key
    best["score"] = scores[best_key]
    return best


@app.post("/package/from-text")
def package_from_text(request: TextPackageRequest) -> dict:
    package = _package_from_text_request(request.text, request.style, request.source_label, _plan_from_request(request))
    data = package.model_dump()
    data["input_source"] = {"kind": "api_text", "source_label": request.source_label}
    return data


@app.post("/generate/from-text/mock")
def generate_from_text_mock(request: TextAceGenerateRequest) -> dict:
    package = _package_from_text_request(request.text, request.style, request.source_label, _plan_from_request(request))
    data = package.model_dump()
    if request.lyrics.strip():
        data["lyric_adaptation_prompt"] = request.lyrics.strip()
    provider = MockSongProvider()
    result = provider.run(_job_from_package(data, request.output_dir, request.duration))
    return {"package": data, "generation": _result_with_url(result)}


@app.post("/generate/from-text/ace")
def generate_from_text_ace(request: TextAceGenerateRequest) -> dict:
    plan = _plan_from_request(request)
    package = _package_from_text_request(request.text, request.style, request.source_label, plan)
    data = package.model_dump()
    if request.lyrics.strip():
        data["lyric_adaptation_prompt"] = request.lyrics.strip()

    # Author mode (product default): build a natural-language brief from the
    # user's idea + the style scaffold + the optional plan, and let ACE-Step's
    # own LM write the lyrics/hook -- no external LLM. A user who supplies their
    # own lyrics and turns author_lyrics off keeps the hand-written path.
    author_lyrics = bool(request.author_lyrics and not request.lyrics.strip())
    brief = ""
    if author_lyrics:
        brief = build_song_brief(STYLE_PRESETS[request.style], request.text, plan)
        data["song_brief"] = brief

    # acemusic.ai is a free, no-SLA upstream whose edge intermittently returns a
    # 504 under load. Each retry re-runs the full (slow) generation, so the stock
    # 3 retries can stretch a single failed request past 4 minutes before giving
    # up -- the "loads forever then fails" symptom. Fail fast instead: one quick
    # retry, then surface a clear "studio busy, try again" so the user can re-fire
    # (a fresh attempt frequently lands when the upstream is less congested).
    # Tunable via ACESTEP_GENERATE_MAX_RETRIES for operators who want more grind.
    generate_max_retries = int(os.getenv("ACESTEP_GENERATE_MAX_RETRIES", "1"))
    try:
        with AceStepApiProvider(
            base_url=request.base_url,
            api_key=request.api_key,
            model=request.model,
            audio_format=request.audio_format,
            vocal_language=request.vocal_language,
            candidates=request.candidates,
            max_retries=generate_max_retries,
        ) as provider:
            result = provider.run(
                _job_from_package(
                    data,
                    request.output_dir,
                    request.duration,
                    author_lyrics=author_lyrics,
                    brief=brief,
                )
            )
    except AceStepApiError as exc:
        raise HTTPException(status_code=502, detail=f"ACE-Step generation failed: {exc}") from exc
    return {"package": data, "generation": _result_with_url(result)}


@app.post("/generate/from-lyrics")
def generate_from_lyrics(request: LyricsGenerateRequest) -> dict:
    """Lyrics-first flow: the user wrote the words, we compose the sound.

    The accent/genre/vibe/voice/tempo choices are composed deterministically into
    a tuned ACE-Step style prompt, and generation uses the hand-written-lyrics
    (tagged) path -- author_lyrics=False -- which is the most reliable ACE-Step
    route and skips the slow LM lyric-authoring step entirely.
    """
    lyrics = request.lyrics.strip()
    if not lyrics:
        raise HTTPException(status_code=400, detail="Lyrics are required -- write at least a line or two.")

    # Two paths: (1) a raw hand-tuned producer-style prompt override, or (2) the
    # standard composed prompt from the tap-to-pick menus. The override path is
    # for one-off high-quality drops where a generic composition isn't enough.
    if request.prompt_override and request.prompt_override.strip():
        prompt_text = request.prompt_override.strip()
        bpm_hint = request.bpm_override or 100
        sound_info = {
            "prompt": prompt_text,
            "bpm": bpm_hint,
            "summary": "Hand-tuned prompt (raw producer spec)",
            "accent": None, "genre": None, "vibe": None,
            "voice": None, "tempo": None, "aesthetic": None,
        }
    else:
        composed = compose_style(
            accent=request.accent,
            genre=request.genre,
            vibe=request.vibe,
            voice=request.voice,
            tempo=request.tempo,
            aesthetic=request.aesthetic,
        )
        prompt_text = composed.prompt
        bpm_hint = request.bpm_override or composed.bpm
        sound_info = {
            "prompt": composed.prompt,
            "bpm": composed.bpm,
            "summary": composed.summary,
            "accent": composed.vocal_style,
            "genre": composed.genre,
            "vibe": composed.vibe,
            "voice": composed.voice,
            "tempo": composed.tempo,
            "aesthetic": composed.aesthetic,
        }

    job = SongJob(
        prompt=prompt_text,
        lyrics=lyrics,
        output_dir=request.output_dir,
        duration_seconds=request.duration,
        bpm_hint=bpm_hint,
        author_lyrics=False,
    )

    generate_max_retries = int(os.getenv("ACESTEP_GENERATE_MAX_RETRIES", "1"))
    try:
        with AceStepApiProvider(
            base_url=request.base_url,
            api_key=request.api_key,
            model=request.model,
            audio_format=request.audio_format,
            vocal_language=request.vocal_language,
            candidates=request.candidates,
            max_retries=generate_max_retries,
            # Default path: thinking/CoT off to stay well under the upstream ~60s
            # gateway timeout (the free acemusic.ai edge kills requests longer).
            # max_quality=True flips them back on for richer generation on the
            # tracks where quality matters more than round-trip speed.
            thinking=request.max_quality,
            use_cot=request.max_quality,
        ) as provider:
            result = provider.run(job)
    except AceStepApiError as exc:
        raise HTTPException(status_code=502, detail=f"ACE-Step generation failed: {exc}") from exc

    return {"sound": sound_info, "lyrics": lyrics, "generation": _result_with_url(result)}


@app.get("/my-tracks", response_class=HTMLResponse)
def my_tracks() -> HTMLResponse:
    """Simple gallery of every generated track still on disk, with proper
    download buttons. Files get wiped when the free-tier instance restarts, so
    this is a "grab it while it's here" page, not a permanent library.
    """
    audio_dir = OUTPUTS_DIR / "audio"
    files: list[dict[str, str | int]] = []
    if audio_dir.exists():
        for path in sorted(audio_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".ogg"}:
                continue
            size_kb = path.stat().st_size // 1024
            files.append({"name": path.name, "url": f"/outputs/audio/{path.name}", "size_kb": size_kb})

    rows = "\n".join(
        f'''<div class="track">
              <div class="meta"><div class="name">🎧 {f["name"]}</div><div class="size">{f["size_kb"]} KB</div></div>
              <div class="btns"><audio controls preload="none" src="{f["url"]}"></audio>
                <a class="btn" href="{f["url"]}" download="{f["name"]}">⬇ Download</a></div>
            </div>'''
        for f in files
    )
    empty = "<p class='empty'>No tracks yet. Go to the home page and make one.</p>" if not files else ""

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>My Tracks — BANGR</title>
<style>
body{{font-family:-apple-system,system-ui,sans-serif;background:#08070c;color:#f6f4ff;margin:0;padding:24px;line-height:1.5}}
.wrap{{max-width:720px;margin:0 auto}}
h1{{font-size:28px;margin:0 0 6px}}
.sub{{color:#9d96b8;margin:0 0 24px;font-size:14px}}
.track{{background:#13111c;border:1px solid #2a2438;border-radius:16px;padding:16px;margin-bottom:12px}}
.meta{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}}
.name{{font-weight:600}}
.size{{color:#6f6789;font-size:12px}}
.btns{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
audio{{flex:1;min-width:220px}}
.btn{{background:linear-gradient(135deg,#ff2d95,#7c3aed);color:#fff;padding:12px 20px;border-radius:999px;text-decoration:none;font-weight:700;font-size:14px;white-space:nowrap}}
.empty{{color:#9d96b8;text-align:center;padding:40px}}
.back{{color:#22d3ee;text-decoration:none;font-weight:600;font-size:13px}}
</style></head>
<body><div class="wrap">
<p><a class="back" href="/">← Back to BANGR</a></p>
<h1>🎧 My Tracks</h1>
<p class="sub">{len(files)} track{"s" if len(files)!=1 else ""} on the server. Tap ⬇ Download to save each one to your phone. <b>Save them soon — the free server wipes files when it sleeps.</b></p>
{rows}{empty}
</div></body></html>"""
    return HTMLResponse(html)


@app.get("/sound-options")
def sound_options() -> dict:
    """Expose the curated menus so the frontend can render the option chips."""
    return {
        "accents": [{"key": v.key, "label": v.label, "suggested_genres": list(v.suggested_genres)} for v in VOCAL_STYLES.values()],
        "genres": [{"key": g.key, "label": g.label} for g in GENRES.values()],
        "vibes": [{"key": v.key, "label": v.label} for v in VIBES.values()],
        "aesthetics": [{"key": a.key, "label": a.label} for a in AESTHETICS.values()],
        "voices": [{"key": k, "label": label} for k, label in VOICES.items()],
        "tempos": [{"key": k, "label": k.capitalize()} for k in TEMPOS],
        "lyric_starters": [{"key": k, "label": v["label"], "lyrics": v["lyrics"]} for k, v in LYRIC_STARTERS.items()],
    }


@app.post("/generate/from-audio/ace")
def generate_from_audio_ace(audio: UploadFile = File(...), prompt: str = Form(...), lyrics: str = Form(""), duration: int = Form(120), base_url: str = Form("https://api.acemusic.ai"), api_key: str = Form(""), model: str = Form("acestep-v15-turbo"), audio_format: str = Form("mp3"), vocal_language: str = Form("en"), task_type: str = Form("cover"), cover_strength: float = Form(0.55)) -> dict:
    allowed_suffixes = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
    original_name = Path(audio.filename or "source_audio.mp3").name
    suffix = Path(original_name).suffix.lower() or ".mp3"
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type: {suffix}")
    if duration < 10 or duration > 600:
        raise HTTPException(status_code=400, detail="Duration must be between 10 and 600 seconds")
    safe_name = f"source-{os.urandom(8).hex()}{suffix}"
    upload_path = UPLOADS_DIR / safe_name
    with upload_path.open("wb") as handle:
        shutil.copyfileobj(audio.file, handle)
    job = SongJob(prompt=prompt.strip(), lyrics=lyrics.strip(), output_dir=OUTPUTS_DIR / "audio", duration_seconds=duration)
    try:
        with AceStepApiProvider(base_url=base_url, api_key=api_key or None, model=model, audio_format=audio_format, vocal_language=vocal_language) as provider:
            result = provider.run_with_audio(job=job, source_audio_path=upload_path, task_type=task_type, cover_strength=cover_strength)
    except AceStepApiError as exc:
        raise HTTPException(status_code=502, detail=f"ACE-Step generation failed: {exc}") from exc
    return {"source_audio": {"filename": original_name, "stored_path": str(upload_path)}, "generation": _result_with_url(result)}


@app.post("/generate/mock")
def generate_mock(request: GenerateRequest) -> dict:
    package_data = _read_package(request.package_path)
    provider = MockSongProvider()
    result = provider.run(_job_from_package(package_data, request.output_dir, request.duration))
    return _result_with_url(result)


@app.post("/generate/ace")
def generate_ace(request: AceGenerateRequest) -> dict:
    package_data = _read_package(request.package_path)
    try:
        with AceStepApiProvider(
            base_url=request.base_url,
            api_key=request.api_key,
            model=request.model,
            audio_format=request.audio_format,
            vocal_language=request.vocal_language,
            candidates=request.candidates,
        ) as provider:
            result = provider.run(_job_from_package(package_data, request.output_dir, request.duration, request.bpm_hint))
    except AceStepApiError as exc:
        raise HTTPException(status_code=502, detail=f"ACE-Step generation failed: {exc}") from exc
    return _result_with_url(result)


@app.post("/score")
def score_version(request: ScoreRequest) -> dict:
    score = VersionScore(artifact_path=request.artifact, version_label=request.version_label, emotion=request.emotion, shareability=request.shareability, vocal_quality=request.vocal_quality, lyrics=request.lyrics, instrumental=request.instrumental, replay_value=request.replay_value, notes=request.notes)
    scorebook = append_score(score, request.scorebook)
    return {"score": score.to_record(), "best": scorebook.get("best")}


@app.post("/improve")
def improve(request: ImproveRequest) -> dict:
    try:
        improved = improve_package(request.package_path, request.scorebook, request.output_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"output_path": str(request.output_path), "improvement_source": improved.get("improvement_source", {})}


def _plan_from_request(request: TextPackageRequest) -> dict | None:
    """Extract the per-song creative fields the frontend forwards from the autopilot plan.

    Returns None (not an empty dict) when every field is blank, so
    build_conversion_package's style-only prompt behavior is preserved for
    callers that never had an autopilot plan (manual studio, plain CLI use).
    """
    fields = {
        "creative_angle": request.creative_angle,
        "mood": request.mood,
        "trend_dna": request.trend_dna,
        "instrumental_notes": request.instrumental_notes,
        "voice_direction": request.voice_direction,
    }
    if not any(value.strip() for value in fields.values()):
        return None
    return fields


def _package_from_text_request(text: str, style: str, source_label: str, plan: dict | None = None):
    if style not in STYLE_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown style: {style}")
    source_text = f"Source label: {source_label}\n\nTreat this as extracted song material. Preserve the emotional meaning, not exact wording.\n\n{text.strip()}"
    return build_conversion_package(source_text=source_text, style_key=style, plan=plan)


def _read_package(package_path: Path) -> dict:
    if not package_path.exists():
        raise HTTPException(status_code=404, detail=f"Package not found: {package_path}")
    return json.loads(package_path.read_text(encoding="utf-8"))


def _job_from_package(
    package_data: dict,
    output_dir: Path,
    duration: int,
    bpm_hint: int | None = None,
    author_lyrics: bool = False,
    brief: str = "",
) -> SongJob:
    prompt = package_data.get("music_prompt", "").strip()
    lyrics = package_data.get("lyric_adaptation_prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Package is missing music_prompt")
    resolved_bpm_hint = bpm_hint if bpm_hint is not None else package_data.get("bpm_hint")
    return SongJob(
        prompt=prompt,
        lyrics=lyrics,
        output_dir=output_dir,
        duration_seconds=duration,
        bpm_hint=resolved_bpm_hint,
        author_lyrics=author_lyrics,
        brief=brief,
    )


def _result_with_url(result: SongJobResult) -> dict:
    data = result.model_dump(mode="json")
    output_path = Path(result.output_path)
    abs_path = output_path if output_path.is_absolute() else ROOT_DIR / output_path
    try:
        relative = abs_path.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        relative = None
    if relative is not None and abs_path.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
        data["audio_url"] = "/outputs/" + relative.as_posix()
    return data
