from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from typing import Any

import httpx

from song_lab.candidate_scoring import select_best_candidate
from song_lab.observability import get_logger, log_with_context, safe_context

logger = get_logger(__name__)

STYLE_KEYS = [
    "dancehall_roast_anthem",
    "diss_track_trap",
    "birthday_banger_pop",
    "love_confession_rnb",
    "breakup_anthem_pop",
    "hype_motivation_anthem",
    "sad_lofi_feels",
    "country_story_love",
]

DEFAULT_NEGATIVE = (
    "weak drums, no hook, long empty intro, robotic vocal, mumbled delivery, "
    "off-beat vocal, messy percussion, noisy mix, random genre switch, copied melody, "
    "copied artist voice, karaoke cover, hate speech, slurs, attacks on protected characteristics"
)

# Retryable HTTP failures: transient overload/rate-limiting. 4xx client errors
# other than 429 (bad request, invalid key) indicate a problem a retry cannot
# fix and must fail fast instead of burning attempts.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_CANDIDATE_COUNT = 3


class AutopilotApiError(RuntimeError):
    """Base error for all autopilot LLM call failures."""


class AutopilotAuthError(AutopilotApiError):
    """Raised on 401/403 -- invalid or missing API key. Never retried."""


class AutopilotClientError(AutopilotApiError):
    """Raised on non-retryable 4xx responses. Never retried."""


class AutopilotRateLimitedError(AutopilotApiError):
    """Raised on 429 after retries are exhausted."""


class AutopilotServerError(AutopilotApiError):
    """Raised on 5xx after retries are exhausted."""


class AutopilotTimeoutError(AutopilotApiError):
    """Raised when a request exceeds its timeout after retries are exhausted."""


class AutopilotInvalidResponseError(AutopilotApiError):
    """Raised when the API returns 200 but the payload is missing or malformed."""


def build_autopilot_plan(
    payload: dict[str, Any],
    client: httpx.Client | None = None,
    candidate_count: int | None = None,
) -> dict[str, Any]:
    """Build a song plan from a raw user prompt.

    When an LLM API key is configured, this requests several candidate
    lyric/hook concepts in a single call and runs them through the
    deterministic heuristic judge (song_lab/candidate_scoring.py) to select
    the most specific, quotable, on-brief one automatically -- this is the
    best-of-N + judge pattern, not a single one-shot guess. Falls back to
    the offline template planner if no key is configured, or if the LLM
    call fails for any reason, so a visitor never sees a hard error.
    """
    user_prompt = str(payload.get("idea") or payload.get("prompt") or "").strip()
    mode = str(payload.get("mode") or "auto").strip().lower()
    avoid = payload.get("avoid") or []
    if not isinstance(avoid, list):
        avoid = []

    api_key = os.getenv("AUTOPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        resolved_count = candidate_count or int(os.getenv("AUTOPILOT_CANDIDATE_COUNT", str(_DEFAULT_CANDIDATE_COUNT)))
        try:
            return _llm_plan(user_prompt=user_prompt, mode=mode, avoid=avoid, api_key=api_key, client=client, candidate_count=resolved_count)
        except Exception as exc:
            log_with_context(
                logger, logging.WARNING, "Autopilot LLM planning failed; falling back to the offline template planner",
                error_type=type(exc).__name__, error=str(exc),
            )
            plan = _prompt_only_fallback(user_prompt=user_prompt, mode=mode)
            plan["planner"] = "prompt_only_fallback_after_llm_error"
            plan["planner_error"] = str(exc)[:260]
            return plan
    return _prompt_only_fallback(user_prompt=user_prompt, mode=mode)


def _build_system_prompt() -> str:
    """System prompt for the candidate-generating LLM call.

    Incorporates two research-backed songwriting principles beyond the
    original version: (1) dimensional specificity -- combining style +
    emotion + instruments + era + production + vocal traits produces more
    consistent, higher-quality output than a single vague genre word (see
    the ACE-Step prompt-engineering literature); (2) TikTok-hook structure --
    the most shareable hooks front-load a concrete, specific detail (a name,
    a real event) rather than a generic affirmation, because generic lines
    are what get skipped past rather than quoted back.
    """
    return (
        "You are an expert songwriter and AI music prompt builder for a viral, shareable song platform. "
        "The user gives one open prompt describing an occasion: a diss/roast track, a birthday song, a love "
        "confession, a breakup anthem, a hype/motivation anthem, sad lo-fi feels, or a country story song. "
        "Infer everything from the prompt only: who/what it's about, vocal style, genre fusion, tempo, "
        "instruments, structure, lyrics, and mix.\n\n"
        "SPECIFICITY IS THE ENTIRE JOB. A song that could apply to any prompt in the same style is a failure, "
        "even if it is well-written. Every candidate must:\n"
        "- Use the actual names, inside jokes, events, and details the user gives you -- never swap in a generic "
        "placeholder line instead.\n"
        "- Open the hook with something concrete and specific, not a generic affirmation. 'Jake blew the "
        "game-winner, we still bring it up' beats 'You had one shot and you blew it twice' -- the first is "
        "impossible to reuse for anyone else's song, the second is a template.\n"
        "- Combine multiple dimensions when describing the sound: genre AND era AND production texture AND "
        "vocal character AND emotion -- 'mid-2000s dancehall riddim with a playful sing-rap flow' produces a "
        "far more consistent result than just 'dancehall'.\n"
        "- Repeat the hook at least twice across the song (once in the Hook section, once in a Hook Repeat) so "
        "it is genuinely chantable and memorable, not a one-off line.\n"
        "- Use clear [Intro]/[Verse]/[Hook]/[Hook Repeat] section tags.\n\n"
        "Return valid JSON only, in the required shape, containing MULTIPLE independent candidate concepts as "
        "instructed in the user message -- do not converge on one 'safe' idea across candidates; give each "
        "candidate a genuinely different angle, hook, or joke so the best one can be selected afterward.\n\n"
        "Use broad music descriptions only. Do not copy real songs, melodies, lyrics, beats, artist voices, "
        "arrangements, or artist likenesses. Lyrics must be natural, singable, catchy, and not cringe, written "
        "in English. If this is a diss/roast track, keep it playful and clever, never hateful, never targeting "
        "protected characteristics, never a real threat -- it should read as a joke between friends, not real "
        "harassment."
    )


def _candidate_shape() -> dict[str, Any]:
    return {
        "style": "one valid backend style id",
        "creative_angle": "specific to the user's prompt",
        "mood": "specific mood",
        "trend_dna": "specific style DNA, no artist copying",
        "instrumental_notes": "specific instruments and production notes, combining genre + era + texture",
        "voice_direction": "voice gender, delivery, singing or rap style",
        "tempo": "BPM/groove recommendation",
        "structure": "short structure with hook timing",
        "concept": "clear concept from user prompt",
        "lyrics": "complete lyrics with [Intro]/[Verse]/[Hook]/[Hook Repeat] sections, hook repeated at least twice",
        "caption": "social caption",
        "hashtags": ["#AIMusic"],
        "story_text": "the hook line itself, short and quotable",
        "meme_text": "optional alternate text",
        "video_idea": "visual/posting idea",
        "why": ["why this specific angle fits"],
        "duration": 45,
    }


def _llm_plan(
    user_prompt: str,
    mode: str,
    avoid: list[Any],
    api_key: str,
    client: httpx.Client | None,
    candidate_count: int,
) -> dict[str, Any]:
    url = os.getenv("AUTOPILOT_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("AUTOPILOT_MODEL", "gpt-4.1-mini")
    max_retries = int(os.getenv("AUTOPILOT_MAX_RETRIES", "2"))

    response_shape = {
        "planner": "llm_best_of_n",
        "candidates": [_candidate_shape() for _ in range(candidate_count)],
    }
    user_content = {
        "user_prompt": user_prompt,
        "mode": mode,
        "avoid": avoid[-6:],
        "candidate_count": candidate_count,
        "required_json_shape": response_shape,
        "valid_style_ids": STYLE_KEYS,
        "instruction": f"Produce exactly {candidate_count} candidates in the 'candidates' array, each with a genuinely different angle/hook/joke.",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ],
        "temperature": 1.0,
        "response_format": {"type": "json_object"},
    }

    owns_client = client is None
    active_client = client or httpx.Client(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0))
    try:
        raw_response = _post_with_retry(active_client, url, body, api_key, max_retries)
    finally:
        if owns_client:
            active_client.close()

    try:
        choice = (raw_response.get("choices") or [{}])[0]
        content = choice["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise AutopilotInvalidResponseError(f"Autopilot LLM response was not in the expected shape: {safe_context(raw_response)}") from exc

    candidates = parsed.get("candidates")
    if not candidates or not isinstance(candidates, list):
        # Tolerate a model that ignored the multi-candidate instruction and
        # returned one flat plan directly -- treat it as a single candidate
        # rather than failing outright.
        if isinstance(parsed, dict) and parsed.get("lyrics"):
            candidates = [parsed]
        else:
            raise AutopilotInvalidResponseError(f"Autopilot LLM response contained no usable candidates: {safe_context(parsed)}")

    normalized_candidates = [_normalize_plan(dict(candidate), user_prompt=user_prompt, planner="llm_best_of_n") for candidate in candidates]

    try:
        best_candidate, all_scores = select_best_candidate(normalized_candidates, source_prompt=user_prompt)
    except ValueError as exc:
        raise AutopilotInvalidResponseError(f"All candidates failed safety/quality checks: {exc}") from exc

    log_with_context(
        logger, logging.INFO, "Selected best-of-N autopilot candidate",
        candidate_count=len(normalized_candidates),
        winning_score=next((s.score for cand, s in zip(normalized_candidates, all_scores) if cand is best_candidate), None),
    )

    best_candidate["planner"] = "llm_best_of_n"
    best_candidate["candidate_count"] = len(normalized_candidates)
    return best_candidate


def _post_with_retry(client: httpx.Client, url: str, body: dict[str, Any], api_key: str, max_retries: int) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    attempt = 0
    while True:
        attempt += 1
        try:
            response = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            if attempt > max_retries:
                raise AutopilotTimeoutError(f"Autopilot request to {url} timed out after {attempt} attempt(s): {exc}") from exc
            _sleep_backoff(attempt)
            continue
        except httpx.TransportError as exc:
            if attempt > max_retries:
                raise AutopilotApiError(f"Could not reach autopilot API at {url} after {attempt} attempt(s): {exc}") from exc
            _sleep_backoff(attempt)
            continue

        if response.status_code in (401, 403):
            raise AutopilotAuthError(f"Autopilot authentication failed: HTTP {response.status_code}")
        if response.status_code in _RETRYABLE_STATUS_CODES:
            if attempt > max_retries:
                error_cls = AutopilotRateLimitedError if response.status_code == 429 else AutopilotServerError
                raise error_cls(f"Autopilot request failed after {attempt} attempt(s): HTTP {response.status_code}")
            _sleep_backoff(attempt)
            continue
        if response.status_code >= 400:
            raise AutopilotClientError(f"Autopilot request rejected: HTTP {response.status_code}: {safe_context(response.text)[:300]}")

        try:
            return response.json()
        except ValueError as exc:
            raise AutopilotInvalidResponseError(f"Autopilot response was not valid JSON: {exc}") from exc


def _sleep_backoff(attempt: int) -> None:
    delay = min(10.0, 1.0 * (2 ** (attempt - 1)))
    time.sleep(delay + random.uniform(0, delay * 0.25))


def _prompt_only_fallback(user_prompt: str, mode: str) -> dict[str, Any]:
    prompt = user_prompt or "Create an original hype song for a friend."
    lower = prompt.lower()
    style = _style_from_prompt(lower, mode)
    duration = _duration_from_prompt(lower)
    voice = _voice_from_prompt(lower)
    vocal_style = _vocal_style_from_prompt(lower, style)
    tempo = _tempo_from_prompt(lower, style)
    instruments = _instruments_from_prompt(prompt)
    mood = _mood_from_prompt(lower, mode, style)
    hook = _hook_from_prompt(prompt, style)
    lyrics = _lyrics_from_prompt(prompt, hook, style)
    plan = {
        "planner": "prompt_only_fallback",
        "style": style,
        "creative_angle": _shorten(prompt, 90),
        "mood": mood,
        "trend_dna": f"Prompt-specific {vocal_style}, {mood}, {tempo}, clear hook, short-form friendly, no preset template.",
        "instrumental_notes": f"{instruments}. Build around the user's requested vibe. Strong first 8 seconds, clean groove, no generic preset feel.",
        "voice_direction": f"{voice}; {vocal_style}; human delivery matched to the prompt.",
        "tempo": tempo,
        "structure": "Intro 0-3s, hook before 8s, short verse, hook repeat, clean ending.",
        "concept": f"Original song based only on this prompt: {prompt}",
        "lyrics": lyrics,
        "caption": _caption_from_style(style),
        "hashtags": _hashtags_from_style(style),
        "story_text": hook,
        "meme_text": "",
        "video_idea": "9:16 story/reel with the hook text on screen in the first second.",
        "why": ["Built from the open prompt only", "No forced preset topic", "Hook-first short-form structure"],
        "duration": duration,
        "negative_prompt": DEFAULT_NEGATIVE,
        "originality_guardrail": "Fully original. Do not copy real songs, melodies, lyrics, beats, arrangements, voices, or artist likenesses. Never hate speech, slurs, or attacks on protected characteristics.",
    }
    return _normalize_plan(plan, user_prompt=prompt, planner=plan["planner"])


def _normalize_plan(plan: dict[str, Any], user_prompt: str, planner: str) -> dict[str, Any]:
    plan = dict(plan or {})
    plan["planner"] = plan.get("planner") or planner
    lower = user_prompt.lower()
    if plan.get("style") not in STYLE_KEYS:
        plan["style"] = _style_from_prompt(lower, "auto")
    try:
        plan["duration"] = int(plan.get("duration") or _duration_from_prompt(lower))
    except Exception:
        plan["duration"] = 45
    if plan["duration"] < 10 or plan["duration"] > 180:
        plan["duration"] = 45
    style = plan["style"]
    plan.setdefault("creative_angle", _shorten(user_prompt, 90))
    plan.setdefault("mood", _mood_from_prompt(lower, "auto", style))
    plan.setdefault("trend_dna", "Prompt-specific style, no preset template.")
    plan.setdefault("instrumental_notes", _instruments_from_prompt(user_prompt))
    plan.setdefault("voice_direction", _voice_from_prompt(lower))
    plan.setdefault("tempo", _tempo_from_prompt(lower, style))
    plan.setdefault("structure", "Intro, hook, verse, hook repeat.")
    plan.setdefault("concept", f"Original song based only on this prompt: {user_prompt}")
    plan.setdefault("lyrics", _lyrics_from_prompt(user_prompt, _hook_from_prompt(user_prompt, style), style))
    plan.setdefault("caption", _caption_from_style(style))
    plan.setdefault("hashtags", _hashtags_from_style(style))
    plan.setdefault("story_text", _hook_from_prompt(user_prompt, style))
    plan.setdefault("meme_text", "")
    plan.setdefault("video_idea", "Post as a short vertical video with hook text immediately visible.")
    plan.setdefault("why", ["Prompt-first", "No preset mode"])
    plan.setdefault("negative_prompt", DEFAULT_NEGATIVE)
    plan["originality_guardrail"] = (
        "Fully original. Do not copy real songs, melodies, lyrics, beats, arrangements, voices, or artist "
        "likenesses. Never hate speech, slurs, or attacks on protected characteristics."
    )
    return plan


def _style_from_prompt(lower: str, mode: str) -> str:
    if mode == "meme" or any(x in lower for x in ["diss", "roast", "clown", "exposed", "ratio"]):
        if any(x in lower for x in ["dancehall", "jamaican", "reggae", "island"]):
            return "dancehall_roast_anthem"
        return "diss_track_trap"
    if any(x in lower for x in ["birthday", "bday", "happy birthday"]):
        return "birthday_banger_pop"
    if any(x in lower for x in ["breakup", "break up", "ex ", "got dumped", "moving on"]):
        return "breakup_anthem_pop"
    if any(x in lower for x in ["love", "crush", "confession", "propose", "anniversary"]):
        return "love_confession_rnb"
    if any(x in lower for x in ["hype", "motivat", "gym", "pump up", "pregame", "grind"]):
        return "hype_motivation_anthem"
    if mode == "sad" or any(x in lower for x in ["sad", "lonely", "heartbroken", "lofi", "lo-fi"]):
        return "sad_lofi_feels"
    if any(x in lower for x in ["country", "story", "hometown", "porch"]):
        return "country_story_love"
    if any(x in lower for x in ["dancehall", "jamaican", "reggae", "island"]):
        return "dancehall_roast_anthem"
    return "hype_motivation_anthem"


def _duration_from_prompt(lower: str) -> int:
    match = re.search(r"(\d{2,3})\s*(?:sec|second|seconds|s)\b", lower)
    if match:
        return max(10, min(180, int(match.group(1))))
    return 45


def _voice_from_prompt(lower: str) -> str:
    if "female" in lower or "girl" in lower or "woman" in lower:
        return "female vocal"
    if "male" in lower or "deep" in lower or "guy" in lower:
        return "male vocal"
    if "duet" in lower:
        return "male and female duet"
    return "auto best-fit vocal"


def _vocal_style_from_prompt(lower: str, style: str) -> str:
    if style in ("diss_track_trap", "hype_motivation_anthem"):
        return "confident rap delivery with a catchy chantable hook"
    if style == "dancehall_roast_anthem":
        return "melodic dancehall sing-rap flow with playful ad-libs"
    if style in ("love_confession_rnb",):
        return "smooth, sincere R&B singing"
    if style == "country_story_love":
        return "warm, conversational storytelling vocal"
    if style == "sad_lofi_feels":
        return "soft, intimate, slightly detached vocal"
    if any(x in lower for x in ["rap", "bars"]):
        return "rap verses with a catchy sung hook"
    return "melodic singing"


def _tempo_from_prompt(lower: str, style: str) -> str:
    from song_lab.presets import STYLE_PRESETS

    preset = STYLE_PRESETS.get(style)
    if preset:
        return f"{preset.tempo_bpm} BPM, {', '.join(preset.mood[:2])} groove"
    if any(x in lower for x in ["dance", "party", "birthday"]):
        return "100-120 BPM, strong groove"
    if any(x in lower for x in ["sad", "slow", "lofi"]):
        return "68-88 BPM, slow emotional groove"
    if any(x in lower for x in ["rap", "trap", "808", "diss"]):
        return "70-106 BPM, tight rap pocket"
    return "76-104 BPM, edit-friendly groove"


def _mood_from_prompt(lower: str, mode: str, style: str) -> str:
    if mode == "meme" or "funny" in lower or style in ("diss_track_trap", "dancehall_roast_anthem"):
        return "playful, savage-but-fun, catchy, social"
    if mode == "sad" or style == "sad_lofi_feels":
        return "melancholic, intimate, cozy-sad"
    if style == "love_confession_rnb":
        return "romantic, warm, sincere"
    if style == "breakup_anthem_pop":
        return "cathartic, empowering, bittersweet-to-triumphant"
    if style == "hype_motivation_anthem":
        return "confident, triumphant, high-energy"
    if style == "birthday_banger_pop":
        return "joyful, celebratory, singalong"
    if style == "country_story_love":
        return "warm, nostalgic, heartfelt"
    return "catchy, polished, prompt-specific"


def _instruments_from_prompt(prompt: str) -> str:
    found = []
    checks = [
        ("dancehall", "dancehall riddim"), ("reggae", "reggae skank guitar"),
        ("808", "808 bass"), ("trap", "trap hi-hats"), ("bass", "bass"),
        ("guitar", "guitar"), ("piano", "piano"), ("drums", "drums"),
        ("claps", "claps"), ("strings", "strings"), ("synth", "synths"),
        ("acoustic", "acoustic guitar"), ("lofi", "lo-fi drum loop"), ("lo-fi", "lo-fi drum loop"),
    ]
    lower = prompt.lower()
    for key, label in checks:
        if key in lower and label not in found:
            found.append(label)
    return ", ".join(found) if found else "Use instruments that best match the user's prompt and chosen style"


def _hook_from_prompt(prompt: str, style: str) -> str:
    short = _shorten(prompt, 42)
    if style == "diss_track_trap":
        return "You had one shot and you blew it twice"
    if style == "dancehall_roast_anthem":
        return "Everybody know you can't compete with me"
    if style == "birthday_banger_pop":
        return "Tonight's your night, we came to celebrate"
    if style == "love_confession_rnb":
        return "I've been meaning to tell you, it's always been you"
    if style == "breakup_anthem_pop":
        return "I'm better off without you, watch me glow"
    if style == "hype_motivation_anthem":
        return "I was built for this, I don't stop, I don't quit"
    if style == "sad_lofi_feels":
        return "Some nights I still reach for a phone that won't ring"
    if style == "country_story_love":
        return "Some stories don't need much, just a little bit of truth"
    return short or "New original hook"


def _lyrics_from_prompt(prompt: str, hook: str, style: str) -> str:
    if style == "diss_track_trap":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nThey said you were the one, turns out that was a joke\n"
            "Talking all that talk but you folded when it's smoke\nI don't even need to try, you did it to yourself\n"
            f"Now it's out here for everybody, on the shelf\n\n[Hook]\n{hook}\nEverybody see it, ain't nothing left to prove\n"
            "You can keep pretending but the receipts don't move\n\n[Verse 2]\nRun it back, replay it, watch it one more time\n"
            f"Every single word of this stayed right on rhyme\n\n[Hook Repeat]\n{hook}\nEverybody see it, ain't nothing left to prove"
        )
    if style == "dancehall_roast_anthem":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nMi hear seh you talking, but the talk nuh match the walk\n"
            "Everybody laughing when dem hear the way you talk\nStep pon di riddim and mi shot it straight and true\n"
            f"\n[Hook]\n{hook}\nWe just having fun but the shot is real\nDance it off, laugh it off, that's the vibe and feel\n"
            f"\n[Verse 2]\nNo hard feelings still, we just keep it light\nBut everybody know who was right tonight\n\n[Hook Repeat]\n{hook}"
        )
    if style == "birthday_banger_pop":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nAnother year down, look how far you've come\nEverybody's here because they love what you've become\n"
            f"\n[Hook]\n{hook}\nMake a wish, blow it out, let the whole room sing\nThis one's for you, celebrate everything\n"
            f"\n[Verse 2]\nHere's to all the memories, here's to what's ahead\nHere's to you tonight, everything I said\n\n[Hook Repeat]\n{hook}"
        )
    if style == "love_confession_rnb":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nI've been running these words over in my mind\nTrying to find the moment, trying to find the time\n"
            f"\n[Hook]\n{hook}\nAnd if you're asking why, I'll tell you every time\nYou're the reason I keep coming back to this line\n"
            f"\n[Verse 2]\nNo, it's not perfect, but it's honest and it's real\nThis is the closest I've come to saying how I feel\n\n[Hook Repeat]\n{hook}"
        )
    if style == "breakup_anthem_pop":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nIt hurt for a minute, I won't lie about that part\nBut I found something stronger sitting in my heart\n"
            f"\n[Hook]\n{hook}\nI'm done looking backwards, I'm done keeping score\nThis is the last time I'm knocking on that door\n"
            f"\n[Verse 2]\nTurns out I was fine, turns out I was strong\nTurns out I've been singing the wrong song for too long\n\n[Hook Repeat]\n{hook}"
        )
    if style == "hype_motivation_anthem":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nWoke up with a purpose, no time to hesitate\nEverything I've dreamed of, I refuse to wait\n"
            f"\n[Hook]\n{hook}\nThis is my moment, I can feel it in my chest\nEverything I've worked for, I'm about to manifest\n"
            f"\n[Verse 2]\nThey can talk all they want, watch me prove it right\nI've been building for this every single night\n\n[Hook Repeat]\n{hook}"
        )
    if style == "sad_lofi_feels":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nIt's 2am again and the room feels too big\nGot the playlist on repeat, same three songs I've dug\n"
            f"\n[Hook]\n{hook}\nI'm okay, I'm okay, I just need a minute more\nSame old feeling knocking on the same old door\n"
            f"\n[Verse 2]\nMaybe it gets better, maybe not tonight\nBut I'm still here, still holding on to the light\n\n[Hook Repeat]\n{hook}"
        )
    if style == "country_story_love":
        return (
            f"[Intro]\n{hook}\n\n[Verse 1]\nGrew up on a back road, nothing fancy, nothing new\nBut I learned more on that porch than in a schoolroom ever knew\n"
            f"\n[Hook]\n{hook}\nAnd if you asked me what mattered, I could tell you in one line\nIt was never about the money, it was always about the time\n"
            f"\n[Verse 2]\nYears go by faster than you think they ever would\nBut some things stay the same, and some things stay for good\n\n[Hook Repeat]\n{hook}"
        )
    return f"[Intro]\n{hook}\n\n[Hook]\n{hook}\n\n[Verse 1]\nOriginal verse built from the prompt.\n\n[Hook Repeat]\n{hook}"


def _caption_from_style(style: str) -> str:
    captions = {
        "diss_track_trap": "This one's not safe 💀🔥 #disstrack",
        "dancehall_roast_anthem": "We just having fun... or are we? 😂🇯🇲",
        "birthday_banger_pop": "Made them a birthday anthem 🎉🎂",
        "love_confession_rnb": "Finally said it... in song form 🥺❤️",
        "breakup_anthem_pop": "New me, new song, no notes 💅",
        "hype_motivation_anthem": "Pull up energy only 🔥",
        "sad_lofi_feels": "For the 2am scroll 🌙",
        "country_story_love": "A little story for you 🎸",
    }
    return captions.get(style, "New original AI song 🔥")


def _hashtags_from_style(style: str) -> list[str]:
    base = ["#AIMusic", "#OriginalSong"]
    extra = {
        "diss_track_trap": ["#DissTrack", "#Roasted"],
        "dancehall_roast_anthem": ["#Dancehall", "#Roasted"],
        "birthday_banger_pop": ["#BirthdaySong", "#HappyBirthday"],
        "love_confession_rnb": ["#LoveSong", "#RNB"],
        "breakup_anthem_pop": ["#BreakupSong", "#GlowUp"],
        "hype_motivation_anthem": ["#HypeSong", "#Motivation"],
        "sad_lofi_feels": ["#LofiVibes", "#SadBoiHours"],
        "country_story_love": ["#CountryMusic", "#StorySong"],
    }
    return base + extra.get(style, [])


def _shorten(text: str, n: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:n]
