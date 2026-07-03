from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

STYLE_KEYS = [
    "arabic_cinematic_epic",
    "arabic_oud_ballad",
    "yemeni_oud_dream_pop",
    "levantine_pop_ballad",
    "khaliji_gulf_pop",
    "yemeni_wedding_modern",
]

DEFAULT_NEGATIVE = (
    "weak drums, no hook, long empty intro, robotic vocal, bad pronunciation, "
    "off-beat vocal, messy percussion, noisy mix, random genre switch, copied melody, "
    "copied artist voice, karaoke cover"
)


def build_autopilot_plan(payload: dict[str, Any]) -> dict[str, Any]:
    user_prompt = str(payload.get("idea") or payload.get("prompt") or "").strip()
    mode = str(payload.get("mode") or "auto").strip().lower()
    avoid = payload.get("avoid") or []
    if not isinstance(avoid, list):
        avoid = []

    api_key = os.getenv("AUTOPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            return _llm_plan(user_prompt=user_prompt, mode=mode, avoid=avoid, api_key=api_key)
        except Exception as exc:
            plan = _prompt_only_fallback(user_prompt=user_prompt, mode=mode)
            plan["planner"] = "prompt_only_fallback_after_llm_error"
            plan["planner_error"] = str(exc)[:260]
            return plan
    return _prompt_only_fallback(user_prompt=user_prompt, mode=mode)


def _llm_plan(user_prompt: str, mode: str, avoid: list[Any], api_key: str) -> dict[str, Any]:
    url = os.getenv("AUTOPILOT_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("AUTOPILOT_MODEL", "gpt-4.1-mini")
    system = (
        "You are an expert AI music prompt builder. The user gives one open prompt. "
        "Do not use presets, do not force a name, and do not force a city. "
        "Infer everything from the prompt only: topic, language, vocal gender, delivery, genre fusion, tempo, instruments, structure, lyrics, and mix. "
        "Return valid JSON only. Make every result fresh and specific to the user's prompt. "
        "Use broad music descriptions only. Do not copy real songs, melodies, lyrics, beats, artist voices, arrangements, or artist likenesses. "
        "Lyrics must be natural, singable, and not cringe. If the user asks English, write English. If Arabic, write Arabic. If unspecified, choose the best fit."
    )
    shape = {
        "planner": "llm_prompt_only",
        "style": "one valid backend style id",
        "creative_angle": "specific to the user's prompt",
        "mood": "specific mood",
        "trend_dna": "specific style DNA, no artist copying",
        "instrumental_notes": "specific instruments and production notes",
        "voice_direction": "voice gender, delivery, singing or rap style",
        "tempo": "BPM/groove recommendation",
        "structure": "short structure with hook timing",
        "concept": "clear concept from user prompt",
        "lyrics": "complete lyrics with sections",
        "caption": "social caption",
        "hashtags": ["#AIMusic"],
        "story_text": "short screen text",
        "meme_text": "optional alternate text",
        "video_idea": "visual/posting idea",
        "why": ["why this fits"],
        "duration": 45,
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"user_prompt": user_prompt, "mode": mode, "avoid": avoid[-6:], "required_json_shape": shape, "valid_style_ids": STYLE_KEYS}, ensure_ascii=False)},
        ],
        "temperature": 0.95,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    data = json.loads(raw)
    content = data["choices"][0]["message"]["content"]
    return _normalize_plan(json.loads(content), user_prompt=user_prompt, planner="llm_prompt_only")


def _prompt_only_fallback(user_prompt: str, mode: str) -> dict[str, Any]:
    prompt = user_prompt or "Create an original social-media song."
    lower = prompt.lower()
    style = _style_from_prompt(lower)
    duration = _duration_from_prompt(lower)
    language = _language_from_prompt(lower)
    voice = _voice_from_prompt(lower)
    vocal_style = _vocal_style_from_prompt(lower)
    tempo = _tempo_from_prompt(lower)
    instruments = _instruments_from_prompt(prompt)
    mood = _mood_from_prompt(lower, mode)
    hook = _hook_from_prompt(prompt, language)
    lyrics = _lyrics_from_prompt(prompt, language, hook, vocal_style)
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
        "caption": "New original AI song idea 🔥",
        "hashtags": ["#AIMusic", "#OriginalSong", "#MusicAI"],
        "story_text": hook,
        "meme_text": "",
        "video_idea": "9:16 story/reel with the hook text on screen in the first second.",
        "why": ["Built from the open prompt only", "No forced name or city", "No preset buttons or preset topic", "Hook-first short-form structure"],
        "duration": duration,
        "negative_prompt": DEFAULT_NEGATIVE,
        "originality_guardrail": "Fully original. Do not copy real songs, melodies, lyrics, beats, arrangements, voices, or artist likenesses.",
    }
    return _normalize_plan(plan, user_prompt=prompt, planner=plan["planner"])


def _normalize_plan(plan: dict[str, Any], user_prompt: str, planner: str) -> dict[str, Any]:
    plan = dict(plan or {})
    plan["planner"] = plan.get("planner") or planner
    if plan.get("style") not in STYLE_KEYS:
        plan["style"] = _style_from_prompt(user_prompt.lower())
    try:
        plan["duration"] = int(plan.get("duration") or _duration_from_prompt(user_prompt.lower()))
    except Exception:
        plan["duration"] = 45
    if plan["duration"] < 10 or plan["duration"] > 180:
        plan["duration"] = 45
    plan.setdefault("creative_angle", _shorten(user_prompt, 90))
    plan.setdefault("mood", _mood_from_prompt(user_prompt.lower(), "auto"))
    plan.setdefault("trend_dna", "Prompt-specific style, no preset template.")
    plan.setdefault("instrumental_notes", _instruments_from_prompt(user_prompt))
    plan.setdefault("voice_direction", _voice_from_prompt(user_prompt.lower()))
    plan.setdefault("tempo", _tempo_from_prompt(user_prompt.lower()))
    plan.setdefault("structure", "Intro, hook, verse, hook repeat.")
    plan.setdefault("concept", f"Original song based only on this prompt: {user_prompt}")
    plan.setdefault("lyrics", _lyrics_from_prompt(user_prompt, _language_from_prompt(user_prompt.lower()), _hook_from_prompt(user_prompt, _language_from_prompt(user_prompt.lower())), _vocal_style_from_prompt(user_prompt.lower())))
    plan.setdefault("caption", "New original AI song idea 🔥")
    plan.setdefault("hashtags", ["#AIMusic", "#OriginalSong"])
    plan.setdefault("story_text", _hook_from_prompt(user_prompt, _language_from_prompt(user_prompt.lower())))
    plan.setdefault("meme_text", "")
    plan.setdefault("video_idea", "Post as a short vertical video with hook text immediately visible.")
    plan.setdefault("why", ["Prompt-first", "No preset mode"])
    plan.setdefault("negative_prompt", DEFAULT_NEGATIVE)
    plan["originality_guardrail"] = "Fully original. Do not copy real songs, melodies, lyrics, beats, arrangements, voices, or artist likenesses."
    return plan


def _style_from_prompt(lower: str) -> str:
    if any(x in lower for x in ["wedding", "زواج", "عرس", "زفة"]):
        return "yemeni_wedding_modern"
    if any(x in lower for x in ["oud", "عود", "sad", "حزين", "ballad", "guitar"]):
        return "arabic_oud_ballad"
    if any(x in lower for x in ["rap", "trap", "funk", "808", "فانك", "راب"]):
        return "khaliji_gulf_pop"
    if any(x in lower for x in ["r&b", "rnb", "pop", "love", "english"]):
        return "levantine_pop_ballad"
    if any(x in lower for x in ["yemeni", "yemen", "يمني", "qanbus", "قنبوس"]):
        return "yemeni_oud_dream_pop"
    return "yemeni_oud_dream_pop"


def _duration_from_prompt(lower: str) -> int:
    match = re.search(r"(\d{2,3})\s*(?:sec|second|seconds|s|ثانية)", lower)
    if match:
        return max(10, min(180, int(match.group(1))))
    return 45


def _language_from_prompt(lower: str) -> str:
    if "english" in lower or "انجليزي" in lower:
        return "english"
    if "arabic" in lower or "عربي" in lower or "يمني" in lower:
        return "arabic"
    return "auto"


def _voice_from_prompt(lower: str) -> str:
    if "female" in lower or "girl" in lower or "woman" in lower or "نسائي" in lower or "بنت" in lower:
        return "female vocal"
    if "male" in lower or "deep" in lower or "رجالي" in lower:
        return "male vocal"
    if "duet" in lower:
        return "male and female duet"
    return "auto best-fit vocal"


def _vocal_style_from_prompt(lower: str) -> str:
    if any(x in lower for x in ["rap", "bars", "راب"]):
        return "rap verses with a catchy sung hook"
    if any(x in lower for x in ["nasheed", "نشيد"]):
        return "chant-like vocal hook"
    if any(x in lower for x in ["r&b", "rnb"]):
        return "smooth R&B singing"
    return "melodic singing"


def _tempo_from_prompt(lower: str) -> str:
    if any(x in lower for x in ["funk", "dance", "wedding", "عرس", "زفة"]):
        return "90-112 BPM, strong groove"
    if any(x in lower for x in ["sad", "slow", "حزين", "slowed"]):
        return "68-88 BPM, slow emotional groove"
    if any(x in lower for x in ["rap", "trap", "808"]):
        return "86-106 BPM, tight rap pocket"
    return "76-104 BPM, edit-friendly groove"


def _mood_from_prompt(lower: str, mode: str) -> str:
    if mode == "meme" or "funny" in lower:
        return "playful, catchy, social"
    if mode == "sad" or "sad" in lower or "حزين" in lower:
        return "emotional, intimate, cinematic"
    if "love" in lower or "حب" in lower:
        return "romantic, warm, catchy"
    if "life" in lower or "hardship" in lower:
        return "hopeful, resilient, emotional"
    return "catchy, polished, prompt-specific"


def _instruments_from_prompt(prompt: str) -> str:
    found = []
    checks = [
        ("oud", "oud"), ("عود", "oud"), ("qanbus", "qanbus"), ("قنبوس", "qanbus"),
        ("funk", "heavy funk bass"), ("bass", "bass"), ("808", "808 bass"),
        ("guitar", "guitar"), ("piano", "piano"), ("drums", "drums"),
        ("claps", "claps"), ("strings", "strings"), ("synth", "synths"),
    ]
    lower = prompt.lower()
    for key, label in checks:
        if key in lower and label not in found:
            found.append(label)
    return ", ".join(found) if found else "Use instruments that best match the user's prompt"


def _hook_from_prompt(prompt: str, language: str) -> str:
    short = _shorten(prompt, 42)
    if language == "english":
        return "I turn the pain into light"
    if language == "arabic":
        return "من التعب يطلع نور"
    return short or "New original hook"


def _lyrics_from_prompt(prompt: str, language: str, hook: str, vocal_style: str) -> str:
    if language == "english":
        return f"[Intro]\n{hook}\n\n[Hook]\n{hook}\nWe keep moving through the night\nEvery scar becomes a sign\nI was low but now I rise\n\n[Verse]\nI had dreams in the dark, kept them close to my chest\nLost a little sleep but I never lost the best\nIf the world gets loud, I still know my lane\nTurn the hurt into rhythm, turn the fire into name\n\n[Hook Repeat]\n{hook}\nWe keep moving through the night\nEvery scar becomes a sign\nI was low but now I rise"
    return f"[Intro]\n{hook}\n\n[Hook]\n{hook}\nوالقلب يمشي رغم كل الظروف\nنغمة قريبة والاحساس معروف\nنرجع نعيد المقطع من جديد\nلما الكلام يصير شعور\n\n[Verse]\nمن أول الطريق والنية دليل\nوالحلم يكبر لو الدرب طويل\nكل ما ضاق الوقت قلنا نصبر\nوالصوت يطلع من قلب أصيل\n\n[Hook Repeat]\n{hook}\nوالقلب يمشي رغم كل الظروف\nنغمة قريبة والاحساس معروف"


def _shorten(text: str, n: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:n]
