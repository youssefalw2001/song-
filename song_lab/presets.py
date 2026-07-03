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
    "arabic_oud_ballad": StylePreset(
        key="arabic_oud_ballad",
        title="Arabic Oud Ballad",
        tempo_bpm="70-88",
        mood=["romantic", "sad", "warm", "cinematic", "intimate"],
        instruments=["oud", "soft strings", "riq", "frame drum", "warm bass", "ambient pad"],
        vocal_direction=(
            "Emotional Arabic lead vocal with clear pronunciation, tasteful melisma, long held chorus notes, "
            "and expressive pauses between phrases."
        ),
        arrangement_notes=[
            "Center the oud and vocal melody.",
            "Keep percussion subtle and supportive.",
            "Use strings to lift the chorus.",
            "Make the hook simple and singable across Arabic dialects.",
        ],
        avoid=["overcrowded percussion", "western EDM drop", "literal translation", "comic exaggeration"],
    ),
    "levantine_pop_ballad": StylePreset(
        key="levantine_pop_ballad",
        title="Levantine Pop Ballad",
        tempo_bpm="82-100",
        mood=["romantic", "modern", "melodic", "emotional", "radio-ready"],
        instruments=["oud", "piano", "strings", "soft pop drums", "bass", "light synth pads"],
        vocal_direction=(
            "Smooth modern Arabic pop vocal with Levantine-style phrasing, clean diction, emotional softness, "
            "and a chorus that feels easy to repeat."
        ),
        arrangement_notes=[
            "Blend Arabic melody with polished pop structure.",
            "Keep verses intimate and let the chorus open wider.",
            "Use oud as color, not necessarily the only lead instrument.",
            "Make the rhythm modern but not too club-heavy.",
        ],
        avoid=["too traditional only", "heavy trap drums", "unclear pronunciation", "stiff formal Arabic"],
    ),
    "egyptian_shaabi_pop": StylePreset(
        key="egyptian_shaabi_pop",
        title="Egyptian Shaabi Pop",
        tempo_bpm="104-124",
        mood=["street", "playful", "energetic", "catchy", "bold"],
        instruments=["accordion", "tabla", "claps", "synth bass", "brass hits", "shaabi percussion"],
        vocal_direction=(
            "Confident Arabic vocal with Egyptian pop attitude, punchy phrasing, clear hooks, and lively callouts."
        ),
        arrangement_notes=[
            "Make the rhythm instantly catchy.",
            "Use short hook lines and repeatable crowd-response moments.",
            "Let accordion or synth lead carry the main riff.",
            "Keep the energy high without losing melodic shape.",
        ],
        avoid=["slow cinematic sadness", "overly classical vocals", "generic Gulf percussion", "too much reverb"],
    ),
    "khaliji_gulf_pop": StylePreset(
        key="khaliji_gulf_pop",
        title="Khaliji Gulf Pop",
        tempo_bpm="88-110",
        mood=["elegant", "rhythmic", "romantic", "desert-night", "polished"],
        instruments=["oud", "khaliji percussion", "claps", "strings", "soft synth", "deep bass"],
        vocal_direction=(
            "Elegant Arabic vocal with Gulf-style rhythmic phrasing, controlled ornamentation, and polished romantic delivery."
        ),
        arrangement_notes=[
            "Use Gulf-inspired percussion patterns as the identity anchor.",
            "Keep the groove rolling and graceful.",
            "Let oud and strings answer vocal phrases.",
            "Make the chorus feel luxurious and spacious.",
        ],
        avoid=["Egyptian shaabi accordion", "Maghrebi rai lead", "too much western rock guitar", "flat vocal delivery"],
    ),
    "maghrebi_rai_fusion": StylePreset(
        key="maghrebi_rai_fusion",
        title="Maghrebi Rai Fusion",
        tempo_bpm="94-118",
        mood=["melancholic", "danceable", "romantic", "raw", "modern"],
        instruments=["rai synth lead", "derbuka", "claps", "electric bass", "strings", "light guitar"],
        vocal_direction=(
            "Expressive Arabic/Maghrebi-style vocal with emotional bends, direct delivery, and a catchy repeated refrain."
        ),
        arrangement_notes=[
            "Balance sadness with movement.",
            "Use a memorable synth or melodic lead hook.",
            "Keep percussion danceable but not overpowering.",
            "Make the refrain direct and easy to remember.",
        ],
        avoid=["formal classical Arabic ballad only", "Yemeni qanbus focus", "slow-only pacing", "over-polished sterile vocal"],
    ),
    "arabic_cinematic_epic": StylePreset(
        key="arabic_cinematic_epic",
        title="Arabic Cinematic Epic",
        tempo_bpm="72-96",
        mood=["powerful", "dramatic", "spiritual", "grand", "emotional"],
        instruments=["oud", "choir", "large strings", "frame drums", "low brass", "cinematic percussion"],
        vocal_direction=(
            "Powerful Arabic lead vocal with dramatic phrasing, wide dynamic range, and optional choir response in the chorus."
        ),
        arrangement_notes=[
            "Start intimate and build to a large cinematic chorus.",
            "Use frame drums and strings for emotional lift.",
            "Add choir responses only where they increase power.",
            "Keep the main melody memorable, not just dramatic texture.",
        ],
        avoid=["small dry mix", "comedy tone", "generic trailer music without Arabic identity", "rushed lyrics"],
    ),
}
