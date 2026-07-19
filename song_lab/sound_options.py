"""Curated 'tap-to-pick' sound options for the lyrics-first flow.

The product pivot: the user writes the lyrics, then picks a vocal style, beat,
vibe, voice, and tempo from small hand-tuned menus. This module holds those
menus and `compose_style()`, a pure function that turns a set of choices into
one tuned ACE-Step style prompt plus a resolved BPM.

Why deterministic composition (no LLM): every fragment here is hand-written and
tested so any combination reads like a coherent studio brief. That makes the
output predictable and removes the fragile 'let a model invent the style' step.
Choices are validated with graceful fallbacks so a bad/unknown key never crashes
generation -- it degrades to a sensible default instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VocalStyle:
    key: str
    label: str
    prompt_fragment: str
    # Genres that pair naturally with this vocal style (surfaced first in the UI).
    suggested_genres: tuple[str, ...] = ()


@dataclass(frozen=True)
class Genre:
    key: str
    label: str
    prompt_fragment: str
    # (slow, medium, fast) BPM anchors; tempo choice selects one.
    bpm: tuple[int, int, int] = (90, 105, 120)


@dataclass(frozen=True)
class Vibe:
    key: str
    label: str
    mood_words: str


# --- Vocal styles / accents ---------------------------------------------------
# Framed as celebrated musical vocal styles (a sound to choose), never a mocking
# impression of a person. Lyrics stay in English; the accent is conveyed through
# the prompt description, not by switching vocal_language.
VOCAL_STYLES: dict[str, VocalStyle] = {
    "jamaican": VocalStyle(
        "jamaican", "Jamaican Dancehall",
        "authentic Jamaican dancehall vocal style, patois-inflected melodic delivery, reggae phrasing and riding the riddim",
        ("dancehall", "afrobeat", "trap"),
    ),
    "bollywood": VocalStyle(
        "bollywood", "Bollywood / Indian",
        "Bollywood-inspired Indian vocal style, expressive filmi melodic runs and ornamented playback-singer phrasing",
        ("pop", "edm", "afrobeat"),
    ),
    "uk_drill": VocalStyle(
        "uk_drill", "UK Drill",
        "UK drill vocal style, British-accented rhythmic flow, slick and understated with sliding cadences",
        ("drill", "trap", "boombap"),
    ),
    "country": VocalStyle(
        "country", "Southern Country",
        "Southern American country vocal style, warm twang and heartfelt storytelling delivery",
        ("country", "pop", "boombap"),
    ),
    "autotune_trap": VocalStyle(
        "autotune_trap", "Auto-Tune Trap",
        "heavily auto-tuned melodic trap vocal style, pitched hooks and modern rage-inflected energy",
        ("trap", "drill", "edm"),
    ),
    "rnb_smooth": VocalStyle(
        "rnb_smooth", "Smooth R&B",
        "smooth soulful R&B vocal style, silky runs, breathy control and intimate tone",
        ("rnb", "pop", "lofi"),
    ),
    "afrobeats": VocalStyle(
        "afrobeats", "Afrobeats",
        "Afrobeats vocal style, melodic West-African inflection with a laid-back pocket groove",
        ("afrobeat", "dancehall", "pop"),
    ),
    "dramatic": VocalStyle(
        "dramatic", "Dramatic / Opera",
        "powerful dramatic operatic vocal style, theatrical vibrato and cinematic dynamics",
        ("edm", "pop", "drill"),
    ),
    # Moody / aesthetic vocal styles for the trend-pack lane. Described by sound
    # only -- never an instruction to imitate a specific real artist's voice.
    "sadgirl_breathy": VocalStyle(
        "sadgirl_breathy", "Sad-Girl Breathy",
        "breathy melancholic female vocal style, intimate reverb-kissed delivery in a sultry lower register with a vintage cinematic-pop feel",
        ("pop", "rnb", "lofi"),
    ),
    "indie_whisper": VocalStyle(
        "indie_whisper", "Indie Whisper",
        "soft whispery indie vocal style, close-mic and intimate with a hazy dreamy tone",
        ("lofi", "pop", "boombap"),
    ),
    "deep_crooner": VocalStyle(
        "deep_crooner", "Deep Crooner",
        "deep smooth crooner vocal style, velvety baritone with warm vintage phrasing",
        ("rnb", "pop", "lofi"),
    ),
}

# --- Genres / beats -----------------------------------------------------------
GENRES: dict[str, Genre] = {
    "trap":      Genre("trap", "Trap", "modern trap production with booming 808 sub-bass, crisp rolling hi-hats and dark synth stabs", (68, 72, 78)),
    "dancehall": Genre("dancehall", "Dancehall / Reggae", "bouncy dancehall reggae riddim with steel pan, deep sub-bass and syncopated claps", (95, 100, 106)),
    "drill":     Genre("drill", "Drill", "drill beat with sliding 808s, dark piano melody and aggressive hi-hats", (138, 142, 146)),
    "afrobeat":  Genre("afrobeat", "Afrobeat", "afrobeats groove with log drums, lively percussion and a warm rolling bassline", (100, 106, 112)),
    "lofi":      Genre("lofi", "Lo-fi", "lo-fi hip hop with dusty vinyl textures, mellow keys and soft laid-back drums", (72, 78, 85)),
    "pop":       Genre("pop", "Pop", "polished modern pop production with bright synths, punchy drums and a radio-ready sheen", (100, 110, 120)),
    "rnb":       Genre("rnb", "R&B", "smooth R&B production with lush chords, finger snaps and a warm bassline", (66, 76, 88)),
    "edm":       Genre("edm", "EDM", "high-energy EDM with festival synth leads, a driving four-on-the-floor kick and a big drop", (120, 124, 128)),
    "country":   Genre("country", "Country", "country production with acoustic guitar, warm bass and live-feel drums", (90, 104, 118)),
    "boombap":   Genre("boombap", "Boom-bap", "boom-bap hip hop with a dusty breakbeat, vinyl crackle and jazzy sampled chords", (86, 90, 95)),
}

# --- Vibes / moods ------------------------------------------------------------
VIBES: dict[str, Vibe] = {
    "funny":       Vibe("funny", "Funny", "playful, funny, comedic and light-hearted"),
    "savage":      Vibe("savage", "Savage / Diss", "savage, confident, cocky and hard-hitting"),
    "romantic":    Vibe("romantic", "Romantic", "romantic, warm, heartfelt and tender"),
    "sad":         Vibe("sad", "Sad", "sad, emotional, melancholic and reflective"),
    "hype":        Vibe("hype", "Hype", "high-energy, hype and explosive"),
    "chill":       Vibe("chill", "Chill", "chill, relaxed, laid-back and mellow"),
    "dark":        Vibe("dark", "Dark", "dark, moody, menacing and cinematic"),
    "triumphant":  Vibe("triumphant", "Triumphant", "triumphant, uplifting, anthemic and victorious"),
    "dreamy":      Vibe("dreamy", "Dreamy", "dreamy, hazy, ethereal and floating"),
    "nostalgic":   Vibe("nostalgic", "Nostalgic", "nostalgic, wistful, bittersweet and vintage"),
    "seductive":   Vibe("seductive", "Seductive", "seductive, sultry, smooth and sensual"),
    "ethereal":    Vibe("ethereal", "Ethereal", "ethereal, celestial, airy and otherworldly"),
    "cinematic":   Vibe("cinematic", "Cinematic", "cinematic, epic, dramatic and sweeping"),
}


@dataclass(frozen=True)
class Aesthetic:
    """An optional trend pack layered on top of genre/vibe.

    Appends a block of production DNA to the composed prompt, and may override the
    tempo (e.g. slowed = slow, sped-up = fast) since those formats are defined by
    their speed. These are the aesthetics that trend on short-form video.
    """

    key: str
    label: str
    prompt_fragment: str
    tempo_override: str | None = None


AESTHETICS: dict[str, Aesthetic] = {
    "none": Aesthetic("none", "None", ""),
    "sadgirl_cinematic": Aesthetic(
        "sadgirl_cinematic", "Sad-Girl Cinematic",
        "cinematic sadcore production, lush orchestral strings, reverb-drenched vintage Hollywood atmosphere, baroque-pop grandeur, dreamy and melancholic",
        tempo_override="slow",
    ),
    "baroque_vintage": Aesthetic(
        "baroque_vintage", "Baroque Vintage",
        "baroque pop with harpsichord arpeggios, a hypnotic waltz-like lilt and warm vintage 60s-70s psychedelic analog texture",
    ),
    "slowed_reverb": Aesthetic(
        "slowed_reverb", "Slowed + Reverb",
        "slowed-down remix feel with heavy reverb, a dreamy hazy spacious atmosphere and immersive depth",
        tempo_override="slow",
    ),
    "sped_up": Aesthetic(
        "sped_up", "Sped-Up",
        "sped-up pitched-up short-form edit feel, bright bouncy and energetic",
        tempo_override="fast",
    ),
    "phonk": Aesthetic(
        "phonk", "Phonk",
        "drift phonk production, distorted cowbell melody, Memphis-style vocal chops, aggressive distorted 808s and lo-fi grit",
    ),
    "dreamy_bedroom": Aesthetic(
        "dreamy_bedroom", "Dreamy Bedroom",
        "dreamy bedroom-pop production, hazy reverb-soaked guitars, lo-fi indie warmth and an intimate whispery atmosphere",
    ),
    "epic_cinematic": Aesthetic(
        "epic_cinematic", "Epic Cinematic",
        "epic cinematic trailer production, huge orchestral swells, a soaring choir, dramatic build and film-score grandeur",
    ),
    "vintage_vinyl": Aesthetic(
        "vintage_vinyl", "Vintage Vinyl",
        "vintage jazz-lounge production, warm vinyl crackle, brushed drums and a smoky nostalgic café mood",
    ),
}

# --- Voice + tempo ------------------------------------------------------------
VOICES: dict[str, str] = {
    "male": "male vocalist",
    "female": "female vocalist",
    "duet": "male and female duet vocals",
}

# Index into a Genre.bpm triple.
TEMPOS: dict[str, int] = {"slow": 0, "medium": 1, "fast": 2}

# Defaults used whenever a choice is missing or unknown.
DEFAULT_VOCAL_STYLE = "rnb_smooth"
DEFAULT_GENRE = "pop"
DEFAULT_VIBE = "hype"
DEFAULT_VOICE = "male"
DEFAULT_TEMPO = "medium"
DEFAULT_AESTHETIC = "none"


@dataclass(frozen=True)
class ComposedStyle:
    prompt: str
    bpm: int
    vocal_style: str
    genre: str
    vibe: str
    voice: str
    tempo: str
    aesthetic: str
    summary: str


def _resolve_bpm(genre: Genre, tempo: str) -> int:
    return genre.bpm[TEMPOS.get(tempo, TEMPOS[DEFAULT_TEMPO])]


def compose_style(
    accent: str | None = None,
    genre: str | None = None,
    vibe: str | None = None,
    voice: str | None = None,
    tempo: str | None = None,
    aesthetic: str | None = None,
) -> ComposedStyle:
    """Turn tap-to-pick choices into one tuned ACE-Step style prompt + BPM.

    Unknown or missing keys fall back to sensible defaults rather than raising,
    so the caller can pass user input straight through. The prompt reads as a
    coherent studio brief: genre + tempo, then voice in the chosen vocal style,
    then mood, then an optional trend-pack aesthetic, then universal quality cues.

    An aesthetic (other than "none") appends a block of production DNA and may
    override the tempo -- e.g. Slowed+Reverb forces a slow tempo, Sped-Up forces
    fast -- since those formats are defined by their speed.
    """
    vocal = VOCAL_STYLES.get(accent or "", VOCAL_STYLES[DEFAULT_VOCAL_STYLE])
    genre_obj = GENRES.get(genre or "", GENRES[DEFAULT_GENRE])
    vibe_obj = VIBES.get(vibe or "", VIBES[DEFAULT_VIBE])
    aesthetic_obj = AESTHETICS.get(aesthetic or "", AESTHETICS[DEFAULT_AESTHETIC])
    voice_key = voice if voice in VOICES else DEFAULT_VOICE

    tempo_key = tempo if tempo in TEMPOS else DEFAULT_TEMPO
    if aesthetic_obj.tempo_override:
        tempo_key = aesthetic_obj.tempo_override
    bpm = _resolve_bpm(genre_obj, tempo_key)

    aesthetic_clause = f"{aesthetic_obj.prompt_fragment}, " if aesthetic_obj.prompt_fragment else ""
    prompt = (
        f"{genre_obj.prompt_fragment}, {bpm} BPM, "
        f"{VOICES[voice_key]} with {vocal.prompt_fragment}, "
        f"{vibe_obj.mood_words} mood, "
        f"{aesthetic_clause}"
        f"strong catchy hook, professional studio quality, crisp clear vocals, clean modern mix, English lyrics"
    )
    summary = f"{vocal.label} \u00b7 {genre_obj.label} \u00b7 {vibe_obj.label} \u00b7 {voice_key} vocals \u00b7 {bpm} BPM"
    if aesthetic_obj.key != DEFAULT_AESTHETIC:
        summary += f" \u00b7 {aesthetic_obj.label}"

    return ComposedStyle(
        prompt=prompt,
        bpm=bpm,
        vocal_style=vocal.key,
        genre=genre_obj.key,
        vibe=vibe_obj.key,
        voice=voice_key,
        tempo=tempo_key,
        aesthetic=aesthetic_obj.key,
        summary=summary,
    )


# --- Fill-in-the-blank lyric starters ----------------------------------------
# Zero-AI writing help: the user edits a working song instead of a blank page.
# [BRACKETS] mark the words they should swap in.
LYRIC_STARTERS: dict[str, dict[str, str]] = {
    "birthday": {
        "label": "Birthday",
        "lyrics": (
            "[Verse 1]\n"
            "Wake up [name], it's finally your day\n"
            "[age] years strong and you did it your way\n"
            "[Chorus]\n"
            "Happy birthday, let the whole world know\n"
            "This one's for you, it's your time to glow\n"
            "[Verse 2]\n"
            "Blow out the candles, make the wish come true\n"
            "Everybody's here 'cause they love you"
        ),
    },
    "diss": {
        "label": "Roast a friend",
        "lyrics": (
            "[Verse 1]\n"
            "Yo [name], let me put you on the spot\n"
            "You said you were the best but you really are not\n"
            "[Chorus]\n"
            "All talk, no game, that's just how you are\n"
            "[name], you a legend? Nah, not by far\n"
            "[Verse 2]\n"
            "Remember [funny thing they did]? We still laugh about that\n"
            "Sit down my friend, and that's a fact"
        ),
    },
    "love": {
        "label": "Love song",
        "lyrics": (
            "[Verse 1]\n"
            "From the moment I met you, [name], I just knew\n"
            "Every little thing feels better with you\n"
            "[Chorus]\n"
            "You're my favorite feeling, my every day\n"
            "[name], I'm not letting you slip away\n"
            "[Verse 2]\n"
            "[a memory you share together] plays in my mind\n"
            "A love like ours is so hard to find"
        ),
    },
    "hype": {
        "label": "Hype anthem",
        "lyrics": (
            "[Verse 1]\n"
            "Lights on, it's go time, no more waiting around\n"
            "[your goal] on my mind, I'm not backing down\n"
            "[Chorus]\n"
            "We up, we up, can't stop us now\n"
            "Watch me get it, I'ma show you how\n"
            "[Verse 2]\n"
            "Every setback was a setup for this\n"
            "Now I'm locked in, there's nothing I'll miss"
        ),
    },
}
