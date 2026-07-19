from __future__ import annotations

from song_lab.models import ConversionPackage, StylePreset
from song_lab.presets import STYLE_PRESETS


LEGAL_SAFETY_NOTE = (
    "Use original, licensed, or public-domain material for public/commercial releases. "
    "Do not clone real singers or imitate living artists without permission. Diss/roast "
    "tracks must target the intended recipient's inside joke or persona playfully -- never "
    "hate speech, slurs, or attacks on protected characteristics."
)


def build_conversion_package(source_text: str, style_key: str) -> ConversionPackage:
    if style_key not in STYLE_PRESETS:
        available = ", ".join(sorted(STYLE_PRESETS))
        raise ValueError(f"Unknown style preset '{style_key}'. Available presets: {available}")

    style = STYLE_PRESETS[style_key]

    return ConversionPackage(
        source_text=source_text,
        style=style,
        analysis_prompt=build_analysis_prompt(source_text),
        lyric_adaptation_prompt=build_lyric_adaptation_prompt(source_text, style.title),
        music_prompt=build_music_prompt(style),
        vocal_prompt=build_vocal_prompt(style),
        scoring_rubric=build_scoring_rubric(),
        iteration_checklist=build_iteration_checklist(),
        legal_safety_note=LEGAL_SAFETY_NOTE,
        bpm_hint=style.bpm_midpoint,
    )


def build_analysis_prompt(source_text: str) -> str:
    return f"""Analyze this song idea without copying any copyrighted lyrics into the output.

Return:
- who/what this song is about and the occasion (diss, birthday, love, breakup, hype, etc.)
- emotional theme
- mood
- tempo estimate
- song structure guess
- strongest hook idea -- the line most likely to get screenshotted or quoted back
- what should be preserved emotionally in the final version

Song idea:
{source_text}
""".strip()


def build_lyric_adaptation_prompt(source_text: str, style_title: str) -> str:
    return f"""Write original English lyrics for a {style_title} version of this idea.

Rules:
- Keep the emotional core and the specific details (names, inside jokes, events) from the source idea.
- Make it singable with short, punchy lines and a repeatable, quotable chorus/hook.
- Front-load the strongest line -- the hook should land in the first 8 seconds.
- Use vivid, specific, personal details instead of generic filler lines.
- If this is a diss/roast track: keep it playful and clever, never hateful, never targeting
  protected characteristics, and clearly framed as a joke between the people involved.
- Avoid directly copying famous lyrics or melodies.

Source idea / vibe:
{source_text}

Output format:
[Verse 1]
...

[Chorus]
...

[Verse 2]
...

[Chorus]
...
""".strip()


def build_music_prompt(style: StylePreset) -> str:
    instruments = ", ".join(style.instruments)
    mood = ", ".join(style.mood)
    arrangement = " ".join(style.arrangement_notes)
    avoid = ", ".join(style.avoid)

    return f"""Create an original song in this style: {style.title}.

Mood: {mood}.
Tempo: {style.tempo_bpm} BPM.
Instruments: {instruments}.
Arrangement: {arrangement}
Avoid: {avoid}.

Make it emotionally strong, replayable, and built to be shared -- the hook should be the
kind of line someone screenshots or quotes back, not generic background music.
""".strip()


def build_vocal_prompt(style: StylePreset) -> str:
    return f"""Vocal direction:
{style.vocal_direction}

Performance notes:
- Sing/deliver with real emotion and personality, not robotic perfection.
- Make every important line clearly audible -- punchlines and hooks must never be mumbled.
- Leave space after key lines for the instrumental to answer.
- Keep pronunciation and diction clear enough to quote back immediately.
""".strip()


def build_scoring_rubric() -> dict[str, str]:
    return {
        "emotion": "Does the version make the listener feel the intended emotion (hype, love, roast-energy, joy, catharsis)? Score 1-10.",
        "shareability": "Would someone actually post or send this to the person it's about? Score 1-10.",
        "vocal_quality": "Is the vocal pleasant, clear, and well-performed for the style? Score 1-10.",
        "lyrics": "Are the lyrics specific, funny/emotional as intended, singable, and not generic filler? Score 1-10.",
        "instrumental": "Does the beat/instrumental feel intentional, catchy, and true to the requested style? Score 1-10.",
        "replay_value": "Would someone replay this voluntarily, or play it for a friend? Score 1-10.",
    }


def build_iteration_checklist() -> list[str]:
    return [
        "Generate at least 3 versions before judging the style.",
        "Pick the strongest hook first; weak verses can be fixed later.",
        "If it sounds generic, add more specific personal details (names, inside jokes, real events).",
        "If the vocal is unclear, simplify the lines and slow the delivery on the hook.",
        "If it feels boring, tighten the hook and get to it faster.",
        "Keep notes for every version so the recipe improves instead of resetting.",
    ]
