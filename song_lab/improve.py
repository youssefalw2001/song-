from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELD_INSTRUCTIONS = {
    "emotion": "Make the performance more emotionally intense: match the delivery to the occasion (bigger hype, deeper sincerity, sharper comedic timing), and build more clearly into the chorus.",
    "shareability": "Make the hook more quotable and screenshot-able: sharpen the funniest/most emotional line, add a more specific personal detail (name, inside joke, real event), and get to it faster.",
    "vocal_quality": "Improve vocal quality: use clearer diction so punchlines/hooks are never mumbled, fewer rushed syllables, and more tasteful delivery for the requested style.",
    "lyrics": "Improve lyrics: simplify the lines, make the chorus more memorable, cut generic filler, and add vivid, specific, personal images.",
    "instrumental": "Improve the instrumental: strengthen the identity of the requested style (the right drums, bass, and lead instrument for that genre), keep percussion clean, and leave space for vocal lines.",
    "replay_value": "Improve replay value: strengthen the hook, repeat the best chorus line, and make the arrangement build more clearly.",
}


def improve_package(package_path: str | Path, scorebook_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    package_file = Path(package_path)
    scorebook_file = Path(scorebook_path)
    destination = Path(output_path)

    package_data = json.loads(package_file.read_text(encoding="utf-8"))
    scorebook = json.loads(scorebook_file.read_text(encoding="utf-8"))
    scores = scorebook.get("scores", [])
    if not scores:
        raise ValueError("Scorebook has no scores. Score at least one version first.")

    latest = scores[-1]
    weak_fields = latest.get("weakest_fields") or _weakest_fields_from_score(latest)
    improvement_notes = [FIELD_INSTRUCTIONS.get(field, f"Improve {field}.") for field in weak_fields]

    suffix = _build_improvement_suffix(latest, weak_fields, improvement_notes)
    package_data["music_prompt"] = _append_section(package_data.get("music_prompt", ""), "Targeted improvement notes", suffix)
    package_data["lyric_adaptation_prompt"] = _append_section(
        package_data.get("lyric_adaptation_prompt", ""),
        "Targeted lyric improvement notes",
        suffix,
    )
    package_data["improvement_source"] = {
        "scorebook": str(scorebook_file),
        "version_label": latest.get("version_label"),
        "weakest_fields": weak_fields,
        "average": latest.get("average"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(package_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return package_data


def _weakest_fields_from_score(score: dict[str, Any]) -> list[str]:
    fields = ["emotion", "shareability", "vocal_quality", "lyrics", "instrumental", "replay_value"]
    values = {field: int(score.get(field, 10)) for field in fields}
    lowest = min(values.values())
    return [field for field, value in values.items() if value == lowest]


def _build_improvement_suffix(latest: dict[str, Any], weak_fields: list[str], notes: list[str]) -> str:
    lines = [
        f"Previous version: {latest.get('version_label', 'unknown')}",
        f"Previous average score: {latest.get('average', 'unknown')}",
        f"Weakest areas: {', '.join(weak_fields)}",
        "User notes:",
        latest.get("notes") or "No notes provided.",
        "Required changes for next generation:",
    ]
    lines.extend(f"- {note}" for note in notes)
    lines.append("Keep what worked, but directly fix the weakest areas. Do not drift into a totally different song.")
    return "\n".join(lines)


def _append_section(original: str, heading: str, body: str) -> str:
    original = original.strip()
    section = f"\n\n## {heading}\n{body}".strip()
    return f"{original}\n\n{section}" if original else section
