from __future__ import annotations

from song_lab.models import ConversionPackage, StylePreset
from song_lab.presets import STYLE_PRESETS


LEGAL_SAFETY_NOTE = (
    "Use original, licensed, or public-domain material for public/commercial releases. "
    "Do not clone real singers or imitate living artists without permission."
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
    )


def build_analysis_prompt(source_text: str) -> str:
    return f"""Analyze this song material without copying any copyrighted lyrics into the output.

Return:
- emotional theme
- mood
- tempo estimate
- song structure guess
- strongest hook idea
- what should be preserved emotionally in a Yemeni-inspired cover

Song material:
{source_text}
""".strip()


def build_lyric_adaptation_prompt(source_text: str, style_title: str) -> str:
    return f"""Create original Arabic lyrics with Yemeni poetic feeling for a {style_title} version.

Rules:
- Preserve the emotional meaning, not the exact wording.
- Do not translate line-by-line.
- Make it singable with short lines and a repeatable chorus.
- Use imagery like night, absence, longing, eyes, heart, distance, silence, and fate.
- Keep the Arabic natural and understandable.
- Avoid directly copying famous lyrics.

Source material / vibe:
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

Make it emotionally strong, replayable, and culturally specific rather than generic Arabic background music.
""".strip()


def build_vocal_prompt(style: StylePreset) -> str:
    return f"""Vocal direction:
{style.vocal_direction}

Performance notes:
- Sing with emotion, not robotic perfection.
- Stretch key words tastefully.
- Leave space after important lines for instrumental answers.
- Keep pronunciation clear enough for Arabic listeners.
""".strip()


def build_scoring_rubric() -> dict[str, str]:
    return {
        "emotion": "Does the version make the listener feel longing, sadness, beauty, or energy? Score 1-10.",
        "yemeni_identity": "Does it feel Yemeni-inspired, not only generic Arabic? Score 1-10.",
        "vocal_beauty": "Is the vocal pleasant, emotional, and clear? Score 1-10.",
        "lyrics": "Are the Arabic lyrics singable, poetic, and natural? Score 1-10.",
        "instrumental": "Do oud/qanbus/percussion/strings feel intentional and musical? Score 1-10.",
        "replay_value": "Would someone replay this voluntarily? Score 1-10.",
    }


def build_iteration_checklist() -> list[str]:
    return [
        "Generate at least 3 versions before judging the style.",
        "Pick the strongest chorus first; weak verses can be fixed later.",
        "If it sounds generic Arabic, strengthen the instrument and rhythm instructions.",
        "If pronunciation is weak, simplify the Arabic lines.",
        "If it feels boring, improve the chorus and oud call-response.",
        "Keep notes for every version so the recipe improves instead of resetting.",
    ]
