"""Deterministic heuristic judge for ranking candidate song plans.

When the autopilot LLM path generates multiple candidate lyric/hook concepts
for the same prompt (best-of-N), something has to pick a winner. Calling the
LLM again to "judge" its own output is slower, costs another API call, and
research on LLM-as-a-judge shows self-evaluation is not reliably better than
a well-designed rubric-based scorer for short, structured text like a song
hook (see LLM-as-a-Judge literature on rubric/pairwise methods). This module
implements that rubric directly as fast, pure, fully-testable Python -- no
network call, no extra cost, deterministic output for the same input.

The scoring dimensions map onto the existing human scoring rubric in
song_lab/scoring.py (emotion, shareability, lyrics, replay_value) but operate
automatically on generated text rather than requiring a human listener.

Safety note: the LLM system prompt (song_lab/autopilot.py) is the PRIMARY
safety control -- it explicitly instructs the model to never produce hate
speech, slurs, or attacks on protected characteristics. This module adds a
defense-in-depth secondary check for a narrow set of unambiguous, high-
severity red flags (self-harm incitement, explicit threats, leaked personal
contact information) that are safe to hardcode without maintaining an actual
slur database in source control. Production systems handling arbitrary user
content should also integrate a dedicated moderation API (e.g. OpenAI's
moderation endpoint) for broader hate-speech/slur coverage; this heuristic
is not a substitute for that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Phrases that show up when an LLM (or a template) defaults to generic filler
# instead of writing something specific to the user's actual idea. Every hit
# lowers the specificity score -- these are exactly the kind of line that
# makes a song forgettable rather than shareable.
GENERIC_FILLER_PHRASES: tuple[str, ...] = (
    "watch me glow",
    "no notes",
    "shining bright",
    "reach for the stars",
    "believe in yourself",
    "living my best life",
    "no more tears to cry",
    "under the moonlight",
    "chasing my dreams",
    "rise and shine",
    "against all odds",
    "one in a million",
    "you had one shot",
    "tonight's your night",
    "i don't stop i don't quit",
)

# Unambiguous, high-severity red flags that must disqualify a candidate
# outright regardless of how well it scores otherwise. Deliberately narrow --
# see module docstring for why a broader slur list does not live here.
_SELF_HARM_INCITEMENT_PATTERNS: tuple[str, ...] = (
    r"\bkill\s+yourself\b",
    r"\bkys\b",
    r"\byou\s+should\s+die\b",
    r"\bhope\s+you\s+die\b",
    r"\bgo\s+die\b",
)
_EXPLICIT_THREAT_PATTERNS: tuple[str, ...] = (
    r"\bi(?:'m|\s+am)\s+going\s+to\s+kill\b",
    r"\bi(?:'ll|\s+will)\s+kill\s+you\b",
    r"\bshow\s+up\s+at\s+your\s+house\b",
)
_PII_LEAK_PATTERNS: tuple[str, ...] = (
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # phone-number-shaped sequence
    r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",  # SSN-shaped sequence
)

_DISQUALIFYING_PATTERN_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("self_harm_incitement", _SELF_HARM_INCITEMENT_PATTERNS),
    ("explicit_threat", _EXPLICIT_THREAT_PATTERNS),
    ("pii_leak", _PII_LEAK_PATTERNS),
)

_STRUCTURE_TAG_PATTERN = re.compile(r"\[(intro|hook|verse|chorus|bridge|outro)[^\]]*\]", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[A-Za-z']+")
_PROPER_NOUN_PATTERN = re.compile(r"\b[A-Z][a-z]{1,20}\b")

# Common sentence-starters and pronouns that capitalization alone would
# otherwise misclassify as a proper noun (name/place) worth rewarding.
_COMMON_CAPITALIZED_WORDS: frozenset[str] = frozenset(
    {
        "I", "The", "A", "An", "And", "But", "For", "So", "Now", "Then", "Every",
        "You", "Your", "We", "It", "This", "That", "These", "Those", "My", "Our",
        "Verse", "Hook", "Chorus", "Intro", "Outro", "Bridge", "Repeat",
    }
)


@dataclass(frozen=True)
class SpecificitySignals:
    """Raw measurements extracted from one candidate's lyrics/hook text."""

    word_count: int
    proper_noun_hits: tuple[str, ...]
    generic_phrase_hits: tuple[str, ...]
    has_structure_tags: bool
    hook_word_count: int
    hook_appears_twice: bool
    source_keyword_overlap: int


@dataclass(frozen=True)
class CandidateScore:
    """Final verdict for one candidate: a score plus the reasoning behind it."""

    score: float
    disqualified: bool
    disqualification_reason: str | None
    signals: SpecificitySignals
    breakdown: dict[str, float] = field(default_factory=dict)


def _extract_source_keywords(source_prompt: str) -> set[str]:
    """Pull the meaningful words out of the user's original prompt.

    Used to reward candidates that actually engage with what the user typed
    (names, specific nouns) rather than drifting into generic filler that
    could apply to any prompt in the same style.
    """
    words = _WORD_PATTERN.findall(source_prompt.lower())
    stopwords = {
        "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
        "my", "me", "i", "is", "it", "this", "that", "song", "about", "45",
        "seconds", "second", "style", "make", "please", "trap", "pop", "rnb",
        "r", "b", "diss", "track", "hype", "anthem", "sad", "happy",
    }
    return {word for word in words if word not in stopwords and len(word) > 2}


def extract_specificity_signals(lyrics: str, hook: str, source_prompt: str) -> SpecificitySignals:
    """Measure the concrete, checkable properties of a candidate's text.

    This is pure text analysis -- no judgment calls happen here, only
    counting. `score_candidate` turns these measurements into a verdict.
    """
    lyrics = lyrics or ""
    hook = hook or ""
    words = _WORD_PATTERN.findall(lyrics)

    proper_noun_hits = tuple(
        sorted(
            {
                match
                for match in _PROPER_NOUN_PATTERN.findall(lyrics)
                if match not in _COMMON_CAPITALIZED_WORDS
            }
        )
    )

    lowered_lyrics = lyrics.lower()
    generic_hits = tuple(phrase for phrase in GENERIC_FILLER_PHRASES if phrase in lowered_lyrics)

    has_structure_tags = bool(_STRUCTURE_TAG_PATTERN.search(lyrics))

    hook_words = _WORD_PATTERN.findall(hook)
    hook_appears_twice = bool(hook.strip()) and lowered_lyrics.count(hook.strip().lower()) >= 2

    source_keywords = _extract_source_keywords(source_prompt)
    lyric_words_lower = {w.lower() for w in words}
    overlap = len(source_keywords & lyric_words_lower)

    return SpecificitySignals(
        word_count=len(words),
        proper_noun_hits=proper_noun_hits,
        generic_phrase_hits=generic_hits,
        has_structure_tags=has_structure_tags,
        hook_word_count=len(hook_words),
        hook_appears_twice=hook_appears_twice,
        source_keyword_overlap=overlap,
    )


def _find_disqualification(lyrics: str, hook: str, caption: str) -> str | None:
    """Return a reason string if the combined text trips a hard safety rule, else None."""
    combined = " ".join([lyrics or "", hook or "", caption or ""]).lower()
    for group_name, patterns in _DISQUALIFYING_PATTERN_GROUPS:
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return group_name
    return None


def score_candidate(candidate: dict, source_prompt: str) -> CandidateScore:
    """Score one candidate plan dict against the shareability/specificity rubric.

    `candidate` is expected to have at least `lyrics` and `story_text` (the
    hook) keys, matching the shape produced by the autopilot planner.
    Disqualified candidates get score=0.0 and must never be selected,
    regardless of how well the rest of their text scores.
    """
    lyrics = candidate.get("lyrics", "") or ""
    hook = candidate.get("story_text", "") or ""
    caption = candidate.get("caption", "") or ""

    disqualification_reason = _find_disqualification(lyrics, hook, caption)
    signals = extract_specificity_signals(lyrics, hook, source_prompt)

    if disqualification_reason:
        return CandidateScore(
            score=0.0,
            disqualified=True,
            disqualification_reason=disqualification_reason,
            signals=signals,
            breakdown={},
        )

    breakdown: dict[str, float] = {}

    # Specificity: does this candidate actually engage with what the user typed,
    # or could it be swapped into any other prompt in the same style unnoticed?
    breakdown["source_engagement"] = min(30.0, signals.source_keyword_overlap * 10.0)
    breakdown["proper_nouns"] = min(20.0, len(signals.proper_noun_hits) * 10.0)

    # Generic filler is a direct penalty -- every hit is a line that will not
    # get quoted back or screenshotted, which is the entire point of this platform.
    breakdown["generic_phrase_penalty"] = -15.0 * len(signals.generic_phrase_hits)

    # Structure: a song without section tags or a hook is not production-ready.
    breakdown["structure"] = 15.0 if signals.has_structure_tags else -10.0
    breakdown["hook_repetition"] = 10.0 if signals.hook_appears_twice else 0.0

    # Hook length: a hook that's too long won't be chantable/quotable; too
    # short (or empty) means the planner didn't actually produce one.
    if signals.hook_word_count == 0:
        breakdown["hook_length"] = -20.0
    elif 3 <= signals.hook_word_count <= 14:
        breakdown["hook_length"] = 15.0
    else:
        breakdown["hook_length"] = -5.0

    # Overall length sanity: guards against a degenerate near-empty response
    # scoring artificially well just because it has no generic phrases to penalize.
    if signals.word_count < 20:
        breakdown["length_sanity"] = -25.0
    elif signals.word_count > 220:
        breakdown["length_sanity"] = -10.0
    else:
        breakdown["length_sanity"] = 5.0

    total = sum(breakdown.values())
    return CandidateScore(
        score=total,
        disqualified=False,
        disqualification_reason=None,
        signals=signals,
        breakdown=breakdown,
    )


def select_best_candidate(candidates: list[dict], source_prompt: str) -> tuple[dict, list[CandidateScore]]:
    """Score every candidate and return the winner alongside the full scoring detail.

    Raises ValueError if the candidate list is empty, or if every candidate
    was disqualified by the safety check -- callers must treat that as a
    hard failure (fall back to the prompt-only path), never silently ship a
    disqualified candidate because it was the "least bad" option.
    """
    if not candidates:
        raise ValueError("select_best_candidate requires at least one candidate.")

    scores = [score_candidate(candidate, source_prompt) for candidate in candidates]
    eligible = [(candidate, score) for candidate, score in zip(candidates, scores) if not score.disqualified]

    if not eligible:
        reasons = {score.disqualification_reason for score in scores if score.disqualification_reason}
        raise ValueError(f"All {len(candidates)} candidate(s) were disqualified by safety checks: {sorted(reasons)}")

    best_candidate, _ = max(eligible, key=lambda pair: pair[1].score)
    return best_candidate, scores
