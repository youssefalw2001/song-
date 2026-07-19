from __future__ import annotations

from song_lab.models import StylePreset


STYLE_PRESETS: dict[str, StylePreset] = {
    "dancehall_roast_anthem": StylePreset(
        key="dancehall_roast_anthem",
        title="Dancehall Roast Anthem",
        tempo_bpm="95-108",
        mood=["playful", "savage-but-fun", "sun-drenched", "confident", "catchy"],
        instruments=[
            "dancehall riddim",
            "steel pan hits",
            "deep sub bass",
            "syncopated clap pattern",
            "vocal chops",
            "bright synth stab",
        ],
        vocal_direction=(
            "Rhythmic, melodic sing-rap delivery with dancehall-style cadence and playful ad-libs. Confident, "
            "comedic, and light-hearted -- never a mocking accent impression, just an energetic, danceable flow "
            "with clear, punchy English lyrics built for a group of friends to laugh and sing along to."
        ),
        arrangement_notes=[
            "Land the funniest line right before the hook drops.",
            "Keep the riddim bouncy and danceable, not aggressive.",
            "Give the chorus a group-chant, sing-back quality.",
            "Use vocal chops or an ad-lib tag as a repeatable meme-able moment.",
            "Hook must land inside the first 8 seconds.",
        ],
        avoid=[
            "hateful or slur-based language",
            "targeting real strangers or protected traits",
            "mocking accent caricature",
            "generic EDM drop",
            "flat, unrhythmic delivery",
        ],
    ),
    "diss_track_trap": StylePreset(
        key="diss_track_trap",
        title="Savage Diss Track",
        tempo_bpm="70-75",
        mood=["aggressive", "confident", "comedic-savage", "high-energy", "cocky"],
        instruments=[
            "808 sub bass",
            "trap hi-hat rolls",
            "dark synth stabs",
            "vocal chop ad-libs",
            "snare rolls",
            "sparse piano stab",
        ],
        vocal_direction=(
            "Confident half-time rap delivery with punchy, clearly enunciated punchlines so every roast line "
            "actually lands. Braggadocious and comedic in tone, built for a friend-group laugh, not real harassment."
        ),
        arrangement_notes=[
            "Every bar should set up a punchline; the best punchline goes right before the hook.",
            "Keep the hook short, chantable, and easy to quote back.",
            "Use 808 bass drops to punctuate the hardest lines.",
            "Leave a beat of silence right before the funniest line for comedic timing.",
        ],
        avoid=[
            "hate speech or slurs",
            "targeting protected characteristics",
            "real threats or harassment content",
            "mumbled, unclear delivery that buries the punchlines",
            "generic trap with no hook",
        ],
    ),
    "birthday_banger_pop": StylePreset(
        key="birthday_banger_pop",
        title="Birthday Banger",
        tempo_bpm="118-128",
        mood=["joyful", "celebratory", "singalong", "confetti-energy", "warm"],
        instruments=[
            "bright synth lead",
            "four-on-the-floor kick",
            "hand claps",
            "punchy pop bass",
            "party horn stabs",
            "shimmering pads",
        ],
        vocal_direction=(
            "Upbeat, warm lead vocal built for a crowd to chant back. The person's name should land clearly and "
            "joyfully in the hook -- this is a song made to be played out loud at their party."
        ),
        arrangement_notes=[
            "Say the birthday person's name in the first line and again in the hook.",
            "Build to a big group-chant chorus by the second hook.",
            "Keep verses light, funny, and specific to the person.",
            "End on the biggest, loudest version of the hook.",
        ],
        avoid=["sad or minor-key tone", "slow ballad pacing", "generic happy-birthday melody quoting", "flat energy"],
    ),
    "love_confession_rnb": StylePreset(
        key="love_confession_rnb",
        title="Love Confession R&B",
        tempo_bpm="68-84",
        mood=["romantic", "warm", "sincere", "intimate", "soulful"],
        instruments=[
            "warm electric piano",
            "soft sub bass",
            "brushed drums",
            "airy string pads",
            "subtle guitar fills",
        ],
        vocal_direction=(
            "Smooth, emotionally sincere R&B vocal with tasteful runs and intimate, close-mic delivery. Every line "
            "should feel like it's being said directly to one specific person, not a generic love song."
        ),
        arrangement_notes=[
            "Keep the verse intimate and conversational.",
            "Let the chorus open up warmer and fuller without losing sincerity.",
            "Use specific, personal details rather than generic love-song cliches.",
            "Leave space after key lines for the instrumental to breathe.",
        ],
        avoid=["cheesy generic love-song cliches", "overly busy arrangement", "cold or robotic delivery", "rushed pacing"],
    ),
    "breakup_anthem_pop": StylePreset(
        key="breakup_anthem_pop",
        title="Breakup Anthem",
        tempo_bpm="100-116",
        mood=["cathartic", "empowering", "bittersweet-to-triumphant", "driving"],
        instruments=[
            "driving pop-rock drums",
            "electric guitar layers",
            "synth stacks",
            "big chorus bass",
            "handclap layer in the chorus",
        ],
        vocal_direction=(
            "Start emotionally raw and vulnerable in the verse, then build to a defiant, empowered, chest-out "
            "delivery by the chorus -- the moment where the listener feels like they've moved on and won."
        ),
        arrangement_notes=[
            "Verse should feel a little wounded; chorus should feel like a release.",
            "Build the arrangement so the second chorus hits bigger than the first.",
            "Give the bridge a turning-point line that flips the emotion from hurt to strength.",
            "End on the most triumphant version of the hook.",
        ],
        avoid=["staying sad and defeated the whole song", "weak or timid chorus", "generic breakup cliches with no specific detail"],
    ),
    "hype_motivation_anthem": StylePreset(
        key="hype_motivation_anthem",
        title="Hype Motivation Anthem",
        tempo_bpm="70-80",
        mood=["confident", "triumphant", "high-energy", "chest-out", "unstoppable"],
        instruments=[
            "massive 808 sub bass",
            "anthemic synth stacks",
            "crowd chant vocal stacks",
            "hard-hitting trap drums",
            "rising synth riser into the hook",
        ],
        vocal_direction=(
            "Confident chant-rap hybrid delivery -- half rapped, half shouted hook -- built for pre-game, gym, or "
            "'about to go handle business' energy. Every line should sound like a declaration, not a suggestion."
        ),
        arrangement_notes=[
            "Open with a bold statement line, no slow build-up.",
            "Make the hook a chantable, all-caps-energy line.",
            "Use a riser or drum roll to launch into every hook.",
            "Keep the whole track feeling like it's building toward one big moment.",
        ],
        avoid=["soft or hesitant delivery", "slow sad tempo", "generic uninspired affirmations", "cluttered mix that buries the vocal"],
    ),
    "sad_lofi_feels": StylePreset(
        key="sad_lofi_feels",
        title="Sad Lo-Fi Feels",
        tempo_bpm="70-90",
        mood=["melancholic", "nostalgic", "cozy-sad", "relatable", "late-night"],
        instruments=[
            "dusty lo-fi drum loop",
            "mellow piano or guitar chords",
            "warm vinyl-texture crackle",
            "soft sub bass",
            "distant ambient pad",
        ],
        vocal_direction=(
            "Soft, intimate, slightly detached vocal delivery -- conversational sadness rather than melodrama. "
            "Should feel like a diary entry set to music, the kind of thing someone posts at 2am."
        ),
        arrangement_notes=[
            "Keep the mix warm, dusty, and low-key -- never polished or bright.",
            "Let the hook be quietly devastating rather than loud.",
            "Use negative space; do not fill every gap with instrumentation.",
            "Keep the vocal close and intimate in the mix.",
        ],
        avoid=["bright pop production", "loud aggressive drums", "overly dramatic vocal performance", "generic sad-song cliches"],
    ),
    "country_story_love": StylePreset(
        key="country_story_love",
        title="Country Story Song",
        tempo_bpm="80-100",
        mood=["warm", "nostalgic", "storytelling", "heartfelt", "down-to-earth"],
        instruments=[
            "acoustic guitar",
            "light steel guitar",
            "warm upright-style bass",
            "simple brushed percussion",
            "subtle harmonica accent",
        ],
        vocal_direction=(
            "Warm, conversational storytelling vocal -- like telling a friend a true story over a porch "
            "conversation. Sincere, plain-spoken, with real specific details rather than vague sentiment."
        ),
        arrangement_notes=[
            "Tell a clear, specific story with a beginning, middle, and a turn.",
            "Keep the instrumentation simple so the story stays the focus.",
            "Let the chorus land as the emotional takeaway of the story.",
            "Use one vivid, specific image the listener will remember.",
        ],
        avoid=["overproduced pop-country sheen", "vague generic lyrics", "busy arrangement that competes with the vocal"],
    ),
}
