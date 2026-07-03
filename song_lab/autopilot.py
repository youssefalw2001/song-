from __future__ import annotations

import json
import os
import random
import re
import time
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

CREATIVE_ANGLES = [
    {
        "key": "aura_pride",
        "style": "arabic_cinematic_epic",
        "title": "Masculine aura / identity pride",
        "dna": "deep male chant, oud/qanbus hit, low cinematic drums, claps, proud identity, heroic hook, strong first 3 seconds, slowed-edit friendly",
        "mood": "proud, masculine, serious, noble, motivational",
        "notes": "Oud/qanbus opening hit, low cinematic drums, firm claps, deep male lead, male response chants, clean 15-second hook loop.",
    },
    {
        "key": "cold_guitar_memory",
        "style": "arabic_oud_ballad",
        "title": "Cold guitar / memory pain",
        "dna": "cold acoustic guitar with oud, intimate vocal, rainy nostalgia, moody bass, sad but beautiful hook, lyric-overlay friendly",
        "mood": "sad, intimate, nostalgic, human, cinematic",
        "notes": "Soft acoustic guitar blended with oud, warm bass, sparse frame drum, rainy pad, vocal enters early, no long intro.",
    },
    {
        "key": "desert_waltz_hypnosis",
        "style": "yemeni_oud_dream_pop",
        "title": "Hypnotic desert waltz",
        "dna": "hypnotic 6/8 or 3/4 sway, plucked oud/qanbus ostinato, vintage desert mystery, warm haze, loopable slowed-edit groove",
        "mood": "mysterious, elegant, nostalgic, hypnotic",
        "notes": "Looping qanbus/oud motif, 6/8 sway, deep bass drone, brushed percussion, warm haze, cinematic desert atmosphere.",
    },
    {
        "key": "dream_slow_edit",
        "style": "yemeni_oud_dream_pop",
        "title": "Dreamy slow edit",
        "dna": "minimal dreamy groove, soft haze, simple phrase repetition, deep space, warm bass, good for slow-motion edits",
        "mood": "dreamy, late-night, smooth, nostalgic",
        "notes": "Minimal drums, airy pads, deep bass, sparse oud phrases, strong hook pocket, good at 0.85x slowed speed.",
    },
    {
        "key": "warm_pop_dedication",
        "style": "levantine_pop_ballad",
        "title": "Warm Arabic pop dedication",
        "dna": "warm Arabic pop melody, sweet chorus, polished percussion, bright oud color, family-friendly dedication, replayable hook",
        "mood": "warm, catchy, emotional, bright",
        "notes": "Bright oud, soft pop drums, claps, strings lift, polished Arabic pop hook, warm vocal tone, family-friendly mix.",
    },
    {
        "key": "wedding_story",
        "style": "yemeni_wedding_modern",
        "title": "Wedding / celebration story",
        "dna": "name shoutout, claps, Yemeni wedding pulse, group response, joy, family pride, social sharing energy",
        "mood": "joyful, celebratory, rhythmic, shareable",
        "notes": "Yemeni wedding rhythm, hand drums, claps, group response, bright oud, short name shoutout, danceable but clean.",
    },
    {
        "key": "meme_majlis",
        "style": "khaliji_gulf_pop",
        "title": "Meme majlis entrance",
        "dna": "funny serious delivery, Gulf/Yemeni claps, exaggerated entrance aura, short punchline hook, clean meme story energy",
        "mood": "funny, confident, playful, dramatic",
        "notes": "Dramatic clap entrance, playful percussion, serious vocal delivery for comedy contrast, short punchline hook, no childish vocals.",
    },
]


def build_autopilot_plan(payload: dict[str, Any]) -> dict[str, Any]:
    user_idea = str(payload.get("idea") or "").strip()
    name = str(payload.get("name") or _extract_name(user_idea) or "محمد علي الفقي").strip()
    city = str(payload.get("city") or _extract_city(user_idea) or "رداع").strip()
    mode = str(payload.get("mode") or "auto").strip().lower()
    avoid = payload.get("avoid") or []
    if not isinstance(avoid, list):
        avoid = []

    api_key = os.getenv("AUTOPILOT_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            return _llm_plan(user_idea=user_idea, name=name, city=city, mode=mode, avoid=avoid, api_key=api_key)
        except Exception as exc:
            fallback = _fallback_plan(user_idea=user_idea, name=name, city=city, mode=mode, avoid=avoid)
            fallback["planner"] = "fallback_after_llm_error"
            fallback["planner_error"] = str(exc)[:220]
            return fallback
    return _fallback_plan(user_idea=user_idea, name=name, city=city, mode=mode, avoid=avoid)


def _llm_plan(user_idea: str, name: str, city: str, mode: str, avoid: list[Any], api_key: str) -> dict[str, Any]:
    url = os.getenv("AUTOPILOT_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("AUTOPILOT_MODEL", "gpt-4.1-mini")
    system = (
        "You are a senior Arabic/Yemeni music creative director for short-form social content. "
        "Return only valid JSON. Create a fresh original song plan, not a template. "
        "Use broad style patterns only. Do not copy or imitate any real artist voice, melody, lyrics, beat, riff, chord progression, hook, or arrangement. "
        "Every plan must be meaningfully different from avoid_previous_outputs. Arabic lyrics must be natural, singable, short, and emotionally clear. "
        "Prioritize name/city in the first 3 seconds, strong rhythm, slowed-edit potential, and IG/Snap/TikTok usability."
    )
    schema_hint = {
        "planner": "llm",
        "style": "one of: " + ", ".join(STYLE_KEYS),
        "creative_angle": "fresh angle name",
        "mood": "short mood string",
        "trend_dna": "broad original style DNA",
        "instrumental_notes": "detailed production notes",
        "concept": "song concept",
        "lyrics": "Arabic lyrics with [Intro], [Hook], [Verse], [Hook Repeat]",
        "caption": "Arabic social caption",
        "hashtags": ["#اليمن"],
        "story_text": "short Arabic screen text",
        "meme_text": "optional meme version screen text",
        "video_idea": "IG/Snap/TikTok visual idea",
        "why": ["reason 1", "reason 2"],
        "duration": 45,
    }
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "user_idea": user_idea,
                    "name": name,
                    "city": city,
                    "mode": mode,
                    "avoid_previous_outputs": avoid[-6:],
                    "required_json_shape": schema_hint,
                },
                ensure_ascii=False,
            ),
        },
    ]
    body = json.dumps(
        {"model": model, "messages": messages, "temperature": 0.95, "response_format": {"type": "json_object"}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=18) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    data = json.loads(raw)
    text = data["choices"][0]["message"]["content"]
    plan = json.loads(text)
    return _normalize_plan(plan, name=name, city=city, planner="llm")


def _fallback_plan(user_idea: str, name: str, city: str, mode: str, avoid: list[Any]) -> dict[str, Any]:
    rng = random.Random(f"{user_idea}|{name}|{city}|{mode}|{time.time_ns()}")
    candidates = [dict(x) for x in CREATIVE_ANGLES]
    avoid_text = " ".join(json.dumps(x, ensure_ascii=False).lower() for x in avoid[-8:])
    for item in candidates:
        item["weight"] = 10
        if item["key"] in avoid_text or item["title"].lower() in avoid_text:
            item["weight"] = 1

    lower = user_idea.lower()
    if mode in {"meme", "funny"} or re.search(r"meme|funny|roast|ضحك|مزح|نكت", lower):
        _boost(candidates, "meme_majlis", 12)
    elif mode in {"wedding", "celebration"} or re.search(r"wedding|زواج|عرس|زفه|زفة|فرح", lower):
        _boost(candidates, "wedding_story", 12)
    elif mode in {"sad", "pain"} or re.search(r"sad|miss|حزين|اشتياق|برد|دموع|وجع", lower):
        _boost(candidates, "cold_guitar_memory", 12)
    elif mode in {"story", "snap", "instagram", "nostalgia"} or re.search(r"story|snap|insta|nostalgia|slowed|edit|ذكرى|قديم", lower):
        _boost(candidates, "desert_waltz_hypnosis", 8)
        _boost(candidates, "dream_slow_edit", 6)
    elif mode in {"pop", "warm"} or re.search(r"pop|nancy|warm|اهداء|dedication", lower):
        _boost(candidates, "warm_pop_dedication", 12)
    else:
        _boost(candidates, "aura_pride", 5)
        _boost(candidates, "desert_waltz_hypnosis", 4)
        _boost(candidates, "meme_majlis", 3)

    angle = rng.choices(candidates, weights=[x["weight"] for x in candidates], k=1)[0]
    hook = rng.choice(_hook_bank(name, city, angle["key"]))
    lyrics = _fresh_lyrics(rng, name=name, city=city, hook=hook, key=angle["key"])
    caption = rng.choice([
        f"سويت أغنية باسم {name} من {city} 🔥 مين أسوي له بعد؟",
        f"{name} من {city} صار له ساوند خاص 😂🔥 اكتب اسمك ومدينتك",
        f"لو اسمك ينحط في أغنية… بتكون كذا؟ {name} من {city} 🇾🇪",
    ])
    plan = {
        "planner": "fallback_randomized",
        "style": angle.get("style", "arabic_cinematic_epic"),
        "creative_angle": angle.get("title", "Fresh Arabic/Yemeni hook"),
        "mood": angle.get("mood", "emotional, catchy, social-story ready"),
        "trend_dna": angle.get("dna", "name early, strong hook, Arabic/Yemeni identity, edit-friendly rhythm"),
        "instrumental_notes": angle.get("notes", "Oud/qanbus, claps, warm bass, clear rhythm, strong hook drop, human Arabic vocal."),
        "concept": f"A fully original Arabic/Yemeni 45-second social-story song about {name} from {city}. User idea: {user_idea}. Creative angle: {angle.get('title', 'fresh hook')}. Make the first line personal and the hook easy to remember after one listen.",
        "lyrics": lyrics,
        "caption": caption,
        "hashtags": ["#اليمن", f"#{city.replace(' ', '_')}", "#اغاني_عربية", "#AImusic", "#سناب", "#انستقرام", "#تيك_توك"],
        "story_text": f"{name} من {city}… هذا الساوند لك 🔥",
        "meme_text": f"POV: {name} من {city} دخل المكان والكل سكت 😂",
        "video_idea": rng.choice([
            "IG/Snap story with name on screen, slow zoom, mountain/car/gym footage, cut every two beats.",
            "Meme story: dramatic entrance text, freeze-frame on the name, then hook drop.",
            "Serious story: black background, gold Arabic text, slow motion clip, name appears on first beat.",
        ]),
        "why": ["Name appears early", "City/identity makes it personal", "Hook is short and repeatable", "45 seconds reduces wasted generations"],
        "duration": 45,
    }
    return _normalize_plan(plan, name=name, city=city, planner=plan["planner"])


def _normalize_plan(plan: dict[str, Any], name: str, city: str, planner: str) -> dict[str, Any]:
    plan = dict(plan or {})
    plan["planner"] = plan.get("planner") or planner
    if plan.get("style") not in STYLE_KEYS:
        plan["style"] = "arabic_cinematic_epic"
    try:
        plan["duration"] = int(plan.get("duration") or 45)
    except Exception:
        plan["duration"] = 45
    if plan["duration"] < 15 or plan["duration"] > 90:
        plan["duration"] = 45
    plan.setdefault("creative_angle", "Fresh Arabic/Yemeni social hook")
    plan.setdefault("mood", "emotional, catchy, social-story ready")
    plan.setdefault("trend_dna", "short hook, name early, Arabic/Yemeni identity, edit-friendly rhythm")
    plan.setdefault("instrumental_notes", "oud/qanbus, claps, warm bass, clear rhythm, strong hook drop")
    plan.setdefault("concept", f"Original Arabic/Yemeni song for {name} from {city}.")
    plan.setdefault("lyrics", _fresh_lyrics(random.Random(time.time_ns()), name, city, f"{name} من {city}", "aura_pride"))
    plan.setdefault("caption", f"سويت أغنية باسم {name} من {city} 🔥")
    plan.setdefault("hashtags", ["#اليمن", "#اغاني_عربية", "#AImusic"])
    plan.setdefault("story_text", f"{name} من {city} 🔥")
    plan.setdefault("meme_text", f"{name} من {city} دخل الترند 😂")
    plan.setdefault("video_idea", "Use 9:16 story format with the name on screen in the first second.")
    plan.setdefault("why", ["Personal", "Short", "Repeatable"])
    plan["originality_guardrail"] = "Fully original. Do not copy real songs, melodies, lyrics, beats, riffs, chord progressions, arrangements, voices, or artist likenesses."
    return plan


def _boost(items: list[dict[str, Any]], key: str, amount: int) -> None:
    for item in items:
        if item.get("key") == key:
            item["weight"] = int(item.get("weight", 0)) + amount


def _hook_bank(name: str, city: str, key: str) -> list[str]:
    if key == "meme_majlis":
        return [f"{name} دخل المجلس", f"من {city} والهيبة زادت", f"وقفوا… {name} وصل"]
    if key == "cold_guitar_memory":
        return [f"يا {name} وينك الليلة", f"اسمك دفا يا {name}", f"من {city} جاني الحنين"]
    if key == "warm_pop_dedication":
        return [f"{name} يا نور المكان", f"يا سلام على {name}", f"من {city} جانا الفرح"]
    if key == "wedding_story":
        return [f"حيّوا {name} يا أهل الكرام", f"زفّوا السلام للي حضر", f"من {city} جانا الفخر"]
    if key in {"desert_waltz_hypnosis", "dream_slow_edit"}:
        return [f"يا {name} يا سر الهيبة", f"{name} من {city} يمشي هدوء", f"والليل يعرف خطوتك"]
    return [f"قم يا {name} وارفع الراية", f"{name} من {city} والهيبة معاه", f"اسمك يرفع الراس"]


def _fresh_lyrics(rng: random.Random, name: str, city: str, hook: str, key: str) -> str:
    verse_lines = {
        "meme_majlis": ["خطوة ثقيلة والجو انقلب", "ضحكة بسيطة والكل انتبه", "ما قال كلمة بس حضوره كفا", "يا ساتر الهيبة دخلت بالغلط"],
        "cold_guitar_memory": ["الغيتار يهمس والعود يرد", "والبرد في صدري يسأل عليك", "كل شارع حافظ اسمك معي", "والليل يرجعني لأول طريق"],
        "warm_pop_dedication": ["ضحكتك تفتح صباح جديد", "والقرب منك شيء سعيد", "كل الأحبة تذكر اسمك", "والخير يمشي لك أكيد"],
        "wedding_story": ["ارفعوا الصوت بالتهاني", "والقلب فرحان يماني", "كل الأحبة حوله اليوم", "والخير مكتوب بالأماني"],
        "desert_waltz_hypnosis": ["في السكون اسمك يبان", "مثل جبل ثابت زمان", "كل ما دار الليل حولك", "تبقى واقف باطمئنان"],
        "dream_slow_edit": ["العود بعيد والصوت قريب", "والقلب يعرف معنى النصيب", "ما يحتاج يرفع صوته كثير", "الهيبة تظهر في الطريق"],
        "aura_pride": ["يا ولد الأصل والطيب معروف", "قلبك ثابت وقت الظروف", "ما تهزك ريح ولا ليل ثقيل", "عزمك العالي دايمًا لك دليل"],
    }
    lines = list(verse_lines.get(key, verse_lines["aura_pride"]))
    rng.shuffle(lines)
    return f"[Intro]\n{name} من {city}\n{hook}\n\n[Hook]\n{hook}\n{name} من {city} والهيبة معاه\nخطوة ثابتة، قلبه دليل\nوالناس تسمع يوم يناداه\n\n[Verse]\n{lines[0]}\n{lines[1]}\n{lines[2]}\n{lines[3]}\n\n[Hook Repeat]\n{hook}\n{name} من {city} والهيبة معاه\nخطوة ثابتة، قلبه دليل\nوالناس تسمع يوم يناداه"


def _extract_name(text: str) -> str | None:
    match = re.search(r"(?:for|باسم|اسمه|name)\s+([\w\s\u0600-\u06FF]{2,40})", text, re.I)
    return match.group(1).strip() if match else None


def _extract_city(text: str) -> str | None:
    match = re.search(r"(?:from|من)\s+([\w\s\u0600-\u06FF]{2,30})", text, re.I)
    return match.group(1).strip() if match else None
