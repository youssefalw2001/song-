from __future__ import annotations

from song_lab.models import StylePreset


STYLE_PRESETS: dict[str, StylePreset] = {
    "yemeni_oud_dream_pop": StylePreset(
        key="yemeni_oud_dream_pop",
        title="Yemeni Oud Dream Pop",
        tempo_bpm="76-84",
        mood=["sad", "hypnotic", "romantic", "night-time", "spacious", "intimate"],
        instruments=[
            "oud",
            "qanbus-style lute",
            "soft frame drum",
            "hand percussion",
            "low strings",
            "ambient pads",
            "warm room reverb",
        ],
        vocal_direction=(
            "Deep emotional Arabic vocal with restrained Yemeni-inspired ornamentation, long held notes, "
            "clear pronunciation, and call-and-response pauses for oud fills."
        ),
        arrangement_notes=[
            "Keep the song slow and spacious.",
            "Let oud or qanbus answer the vocal after important lines.",
            "Use percussion as pulse, not as a loud dance beat.",
            "Keep the dream-pop atmosphere, but replace western brightness with warmer acoustic texture.",
            "Chorus should be simple, memorable, and repeatable.",
        ],
        avoid=[
            "generic belly-dance rhythm",
            "trap drums in the first version",
            "overly classical Arabic phrasing",
            "literal translation",
            "fake famous-singer voice cloning",
        ],
    ),
    "yemeni_wedding_modern": StylePreset(
        key="yemeni_wedding_modern",
        title="Modern Yemeni Wedding Energy",
        tempo_bpm="96-112",
        mood=["joyful", "communal", "percussive", "bright", "celebratory"],
        instruments=["oud", "hand drums", "claps", "mizmar-like lead", "bass", "group chorus"],
        vocal_direction="Confident Arabic lead vocal with group responses and celebratory energy.",
        arrangement_notes=[
            "Make rhythm and chorus the center.",
            "Use group chant responses after lead vocal lines.",
            "Keep hook short and easy to sing at a gathering.",
        ],
        avoid=["slow dream-pop pads", "too much sadness", "western pop-only drums"],
    ),
}
