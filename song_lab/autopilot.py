from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

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
        "You are an expert AI music prompt builder for a viral, shareable song platform. The user gives one "
        "open prompt describing an occasion: a diss/roast track, a birthday song, a love confession, a breakup "
        "anthem, a hype/motivation anthem, sad lo-fi feels, or a country story song. Infer everything from the "
        "prompt only: who/what it's about, vocal style, genre fusion, tempo, instruments, structure, lyrics, "
        "and mix. Return valid JSON only. Make every result fresh and specific to the user's prompt -- lean "
        "into specific names, inside jokes, and real details the user gives you. "
        "Use broad music descriptions only. Do not copy real songs, melodies, lyrics, beats, artist voices, "
        "arrangements, or artist likenesses. "
        "Lyrics must be natural, singable, catchy, and not cringe, written in English. If this is a diss/roast "
        "track, keep it playful and clever, never hateful, never targeting protected characteristics -- it "
        "should read as a joke between friends, not real harassment."
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
