from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELD_INSTRUCTIONS = {
    "emotion": "Make the performance more emotionally intense: slower phrasing, more longing, warmer reverb, and stronger rise into the chorus.",
    "yemeni_identity": "Make the result more specifically Yemeni: emphasize qanbus or oud phrases, hand percussion, call-and-response, and natural Yemeni poetic phrasing.",
    "vocal_beauty": "Improve vocal beauty: use a smoother emotional Arabic voice, clearer pronunciation, fewer rushed syllables, and more tasteful held notes.",
    "lyrics": "Improve lyrics: simplify the lines, make the chorus more memorable, avoid literal translation, and use natural Arabic/Yemeni poetic images.",
    "instrumental": "Improve the instrumental: reduce generic Arabic-pop elements, add warmer oud/qanbus details, keep percussion soft, and leave space for vocal lines.",
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
    fields = ["emotion", "yemeni_identity", "vocal_beauty", "lyrics", "instrumental", "replay_value"]
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
