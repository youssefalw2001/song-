from __future__ import annotations

from typing import Any

from song_lab.models import ConversionPackage, StylePreset
from song_lab.presets import STYLE_PRESETS


LEGAL_SAFETY_NOTE = (
    "Use original, licensed, or public-domain material for public/commercial releases. "
    "Do not clone real singers or imitate living artists without permission. Diss/roast "
    "tracks must target the intended recipient's inside joke or persona playfully -- never "
    "hate speech, slurs, or attacks on protected characteristics."
)

# Keys read from an autopilot plan dict when merging it into the music/vocal
# prompts. Kept as a single source of truth so build_music_prompt and
# build_vocal_prompt agree on the plan's shape.
_PLAN_CREATIVE_ANGLE_KEY = "creative_angle"
_PLAN_MOOD_KEY = "mood"
_PLAN_TREND_DNA_KEY = "trend_dna"
_PLAN_INSTRUMENTAL_NOTES_KEY = "instrumental_notes"
_PLAN_VOICE_DIRECTION_KEY = "voice_direction"


def build_conversion_package(source_text: str, style_key: str, plan: dict[str, Any] | None = None) -> ConversionPackage:
    """Build the full prompt package for one song.

    `plan` is the per-song creative output from the autopilot planner
    (song_lab/autopilot.py) -- creative_angle, mood, trend_dna,
    instrumental_notes, voice_direction. When provided, it is merged into
    the music and vocal prompts on top of the style preset's fixed
    scaffold, so two songs using the same style preset (e.g. two diss
    tracks) still produce genuinely different instructions to the audio
    model instead of near-identical ones that only differ in lyrics.
    `plan` is optional and defaults to None so existing callers (the CLI,
    manual/no-plan API requests) are unaffected and get the original
    style-only prompts.
    """
    if style_key not in STYLE_PRESETS:
        available = ", ".join(sorted(STYLE_PRESETS))
        raise ValueError(f"Unknown style preset '{style_key}'. Available presets: {available}")

    style = STYLE_PRESETS[style_key]

    return ConversionPackage(
        source_text=source_text,
        style=style,
        analysis_prompt=build_analysis_prompt(source_text),
        lyric_adaptation_prompt=build_lyric_adaptation_prompt(source_text, style.title),
        music_prompt=build_music_prompt(style, plan),
        vocal_prompt=build_vocal_prompt(style, plan),
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


def build_song_brief(style: StylePreset, idea: str, plan: dict[str, Any] | None = None) -> str:
    """Fuse the user's idea + style scaffold + guardrails into one natural-language brief.

    This brief is what gets handed to ACE-Step's own built-in language model
    (via sample_mode) so the model authors the actual lyrics and hook itself,
    tailored to this specific prompt -- no external LLM required. Everything
    the model needs is expressed in plain natural language rather than tags,
    because sample_mode reads a free-text query: the occasion and the user's
    concrete details (names, inside jokes, events), the musical style pulled
    from the preset scaffold, the per-song creative direction from the
    optional plan, and the safety guardrails.
    """
    plan = plan or {}
    idea = (idea or "").strip()

    instruments = ", ".join(style.instruments)
    baseline_mood = ", ".join(style.mood)
    plan_mood = str(plan.get(_PLAN_MOOD_KEY) or "").strip()
    creative_angle = str(plan.get(_PLAN_CREATIVE_ANGLE_KEY) or "").strip()
    trend_dna = str(plan.get(_PLAN_TREND_DNA_KEY) or "").strip()
    instrumental_notes = str(plan.get(_PLAN_INSTRUMENTAL_NOTES_KEY) or "").strip()
    voice_direction = str(plan.get(_PLAN_VOICE_DIRECTION_KEY) or "").strip()

    mood = plan_mood or baseline_mood
    angle = creative_angle or idea

    lines = [
        f"Write a complete, original {style.title}.",
        f"What it is about: {idea}." if idea else "",
        f"Specific creative angle: {angle}." if angle and angle != idea else "",
        f"Musical style: {style.tempo_bpm} BPM, {instruments}.",
        f"Extra instrumental direction: {instrumental_notes}." if instrumental_notes else "",
        f"Style DNA: {trend_dna}." if trend_dna else "",
        f"Mood: {mood}.",
        f"Vocal delivery: {voice_direction or style.vocal_direction}",
        "Structure the lyrics with clear [Intro], [Verse], [Hook], and a repeated [Hook] section, "
        "and make the hook short, catchy, and quotable.",
        "Keep it playful, clever, and PG-13. Never hateful, never slurs, never attacks on protected "
        "characteristics, never a real threat -- a diss stays a joke between friends.",
        "Fully original: do not copy real songs, melodies, lyrics, beats, or artist likenesses.",
        "Write the lyrics in English.",
    ]
    return "\n".join(line for line in lines if line)


def build_music_prompt(style: StylePreset, plan: dict[str, Any] | None = None) -> str:
    """Build the music-generation prompt sent to the audio model.

    The style preset supplies the fixed genre scaffold (instruments, BPM
    range, arrangement rules, what to avoid) so the output stays coherent
    with the requested style. When a plan is supplied, its per-song
    creative_angle/mood/trend_dna/instrumental_notes are layered on top so
    the specific vibe of THIS song (funny vs. hard vs. petty, dancehall-
    leaning vs. trap-leaning, playful ad-libs vs. cold and clinical) reaches
    the audio model instead of being discarded after the lyrics step.
    """
    instruments = ", ".join(style.instruments)
    mood = ", ".join(style.mood)
    arrangement = " ".join(style.arrangement_notes)
    avoid = ", ".join(style.avoid)

    plan = plan or {}
    creative_angle = str(plan.get(_PLAN_CREATIVE_ANGLE_KEY) or "").strip()
    plan_mood = str(plan.get(_PLAN_MOOD_KEY) or "").strip()
    trend_dna = str(plan.get(_PLAN_TREND_DNA_KEY) or "").strip()
    instrumental_notes = str(plan.get(_PLAN_INSTRUMENTAL_NOTES_KEY) or "").strip()

    vibe_lines = []
    if creative_angle:
        vibe_lines.append(f"This song's specific angle: {creative_angle}")
    if plan_mood:
        vibe_lines.append(f"This song's specific mood (on top of the style's baseline mood): {plan_mood}")
    if trend_dna:
        vibe_lines.append(f"This song's specific style DNA: {trend_dna}")
    if instrumental_notes:
        vibe_lines.append(f"This song's specific instrumental direction: {instrumental_notes}")
    vibe_section = ("\n" + "\n".join(vibe_lines) + "\n") if vibe_lines else ""

    return f"""Create an original song in this style: {style.title}.
{vibe_section}
Mood (style baseline): {mood}.
Tempo: {style.tempo_bpm} BPM.
Instruments (style baseline): {instruments}.
Arrangement: {arrangement}
Avoid: {avoid}.

Make it emotionally strong, replayable, and built to be shared -- the hook should be the
kind of line someone screenshots or quotes back, not generic background music. This song
must sound distinct from other songs in the same style -- lean into its specific angle above,
not just the genre's general conventions.
""".strip()


def build_vocal_prompt(style: StylePreset, plan: dict[str, Any] | None = None) -> str:
    """Build the vocal-direction prompt sent to the audio model.

    Same merge principle as build_music_prompt: the style preset's
    vocal_direction is the baseline delivery for the genre, and the plan's
    voice_direction (when supplied) layers this specific song's vocal
    character on top -- so, for example, two diss tracks in the same style
    can still sound mocking vs. cold vs. gleeful depending on what the
    autopilot planner decided fit this specific prompt.
    """
    plan = plan or {}
    voice_direction = str(plan.get(_PLAN_VOICE_DIRECTION_KEY) or "").strip()
    specific_section = f"\nThis song's specific vocal character: {voice_direction}\n" if voice_direction else ""

    return f"""Vocal direction (style baseline):
{style.vocal_direction}
{specific_section}
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
