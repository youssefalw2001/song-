from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


SCORE_FIELDS = (
    "emotion",
    "shareability",
    "vocal_quality",
    "lyrics",
    "instrumental",
    "replay_value",
)


class VersionScore(BaseModel):
    version_label: str
    artifact_path: str
    emotion: int = Field(ge=1, le=10)
    shareability: int = Field(ge=1, le=10)
    vocal_quality: int = Field(ge=1, le=10)
    lyrics: int = Field(ge=1, le=10)
    instrumental: int = Field(ge=1, le=10)
    replay_value: int = Field(ge=1, le=10)
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def calculate_average(self) -> "VersionScore":
        return self

    @property
    def average(self) -> float:
        total = sum(getattr(self, field) for field in SCORE_FIELDS)
        return round(total / len(SCORE_FIELDS), 2)

    @property
    def passed(self) -> bool:
        return (
            self.emotion >= 8
            and self.shareability >= 8
            and self.vocal_quality >= 7
            and self.lyrics >= 7
            and self.instrumental >= 7
            and self.replay_value >= 7
        )

    def to_record(self) -> dict:
        data = self.model_dump()
        data["average"] = self.average
        data["passed"] = self.passed
        data["weakest_fields"] = self.weakest_fields()
        data["next_action"] = self.next_action()
        return data

    def weakest_fields(self) -> list[str]:
        values = {field: getattr(self, field) for field in SCORE_FIELDS}
        minimum = min(values.values())
        return [field for field, value in values.items() if value == minimum]

    def next_action(self) -> str:
        weak = set(self.weakest_fields())
        if "shareability" in weak:
            return "Sharpen the hook into something more quotable/screenshot-able; add a more specific, personal detail."
        if "vocal_quality" in weak:
            return "Try a different vocal direction, simpler lyrics, or a different style preset."
        if "lyrics" in weak:
            return "Rewrite the chorus and add more specific, personal detail instead of generic lines."
        if "instrumental" in weak:
            return "Adjust instrumentation and arrangement to better match the requested style's identity."
        if "replay_value" in weak:
            return "Improve the hook and chorus repetition; get to the best line faster."
        return "Keep this version as a candidate and generate one close variation."


def append_score(score: VersionScore, scorebook_path: str | Path) -> dict:
    path = Path(scorebook_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        scorebook = json.loads(path.read_text(encoding="utf-8"))
    else:
        scorebook = {"scores": []}

    scorebook.setdefault("scores", []).append(score.to_record())
    scorebook["best"] = best_score(scorebook["scores"])
    path.write_text(json.dumps(scorebook, ensure_ascii=False, indent=2), encoding="utf-8")
    return scorebook


def best_score(scores: list[dict]) -> dict | None:
    if not scores:
        return None
    return sorted(scores, key=lambda item: item.get("average", 0), reverse=True)[0]
