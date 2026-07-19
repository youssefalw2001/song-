from __future__ import annotations

import json
from pathlib import Path

import click

from song_lab.audio.jobs import SongJob
from song_lab.improve import improve_package
from song_lab.pipeline import build_conversion_package
from song_lab.presets import STYLE_PRESETS
from song_lab.providers.ace_step_api import AceStepApiError, AceStepApiProvider
from song_lab.providers.mock import MockSongProvider
from song_lab.scoring import VersionScore, append_score


@click.group()
def main() -> None:
    """Yemeni Song Conversion Lab command line tools."""


@main.command("package")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to lyrics, notes, or song-vibe text.",
)
@click.option(
    "--style",
    default="yemeni_oud_dream_pop",
    show_default=True,
    type=click.Choice(sorted(STYLE_PRESETS.keys())),
    help="Target Yemeni-inspired style preset.",
)
@click.option(
    "--output",
    "output_path",
    default="outputs/test-package.json",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Where to write the generated test package JSON.",
)
def package_command(input_path: str, style: str, output_path: str) -> None:
    """Create a repeatable prompt package for Yemeni-style song conversion."""
    source_text = _read_text_input(input_path)
    package = build_conversion_package(source_text=source_text, style_key=style)
    _write_package(package.model_dump(), output_path)
    click.echo(f"Wrote conversion test package: {output_path}")
    click.echo("Next: run mock-audio or ace-audio to generate an artifact.")


@main.command("from-text")
@click.option(
    "--text-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to an extracted lyric, transcript, or vibe-notes text file.",
)
@click.option(
    "--style",
    default="yemeni_oud_dream_pop",
    show_default=True,
    type=click.Choice(sorted(STYLE_PRESETS.keys())),
    help="Target Yemeni-inspired style preset.",
)
@click.option(
    "--output",
    "output_path",
    default="outputs/from-text-package.json",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Where to write the package JSON.",
)
@click.option(
    "--source-label",
    default="user_text_input",
    show_default=True,
    help="Label used in package metadata.",
)
def from_text_command(text_file: str, style: str, output_path: str, source_label: str) -> None:
    """Build a Yemeni conversion package from existing text extracted from a song."""
    source_text = _read_text_input(text_file)
    enriched = (
        f"Source label: {source_label}\n\n"
        "Treat this as extracted song material. Preserve the emotional meaning, not exact wording.\n\n"
        f"{source_text}"
    )
    package = build_conversion_package(source_text=enriched, style_key=style)
    data = package.model_dump()
    data["input_source"] = {"kind": "text_file", "path": text_file, "source_label": source_label}
    _write_package(data, output_path)
    click.echo(f"Wrote text-derived conversion package: {output_path}")


@main.command("mock-audio")
@click.option(
    "--package",
    "package_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a package JSON created by the package command.",
)
@click.option(
    "--output-dir",
    default="outputs/audio",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Where to write mock generation output.",
)
@click.option("--duration", default=90, show_default=True, type=int, help="Target song duration in seconds.")
def mock_audio_command(package_path: str, output_dir: str, duration: int) -> None:
    """Run the current end-to-end flow without a real music model yet."""
    package_data = _read_package(package_path)
    provider = MockSongProvider()
    result = provider.run(_job_from_package(package_data, output_dir, duration))
    click.echo(result.model_dump_json(indent=2))


@main.command("ace-audio")
@click.option(
    "--package",
    "package_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a package JSON created by the package command.",
)
@click.option(
    "--output-dir",
    default="outputs/audio",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Where to write ACE-Step output.",
)
@click.option("--base-url", default="http://127.0.0.1:8001", show_default=True, help="ACE-Step API server URL.")
@click.option("--api-key", default=None, help="Optional ACE-Step API key.")
@click.option("--model", default="acestep-v15-turbo", show_default=True, help="ACE-Step model name.")
@click.option("--duration", default=90, show_default=True, type=int, help="Target song duration in seconds.")
@click.option("--format", "audio_format", default="mp3", show_default=True, help="Output audio format, e.g. mp3 or wav.")
@click.option("--vocal-language", default="ar", show_default=True, help="Vocal language code for lyrics.")
@click.option("--bpm-hint", default=None, type=int, help="Optional target BPM. Defaults to the package's bpm_hint if present.")
@click.option("--candidates", default=1, show_default=True, type=click.IntRange(1, 4), help="Generate N takes and keep the one closest to the requested duration.")
def ace_audio_command(
    package_path: str,
    output_dir: str,
    base_url: str,
    api_key: str | None,
    model: str,
    duration: int,
    audio_format: str,
    vocal_language: str,
    bpm_hint: int | None,
    candidates: int,
) -> None:
    """Generate real audio using a running ACE-Step API server."""
    package_data = _read_package(package_path)
    try:
        with AceStepApiProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            audio_format=audio_format,
            vocal_language=vocal_language,
            candidates=candidates,
        ) as provider:
            result = provider.run(_job_from_package(package_data, output_dir, duration, bpm_hint))
    except AceStepApiError as exc:
        raise click.ClickException(f"ACE-Step generation failed: {exc}") from exc
    click.echo(result.model_dump_json(indent=2))


@main.command("score-version")
@click.option("--artifact", required=True, help="Path or label for the generated version being scored.")
@click.option("--version-label", required=True, help="Human-readable version name, e.g. v1-dream-oud.")
@click.option("--emotion", required=True, type=click.IntRange(1, 10))
@click.option("--yemeni-identity", required=True, type=click.IntRange(1, 10))
@click.option("--vocal-beauty", required=True, type=click.IntRange(1, 10))
@click.option("--lyrics", required=True, type=click.IntRange(1, 10))
@click.option("--instrumental", required=True, type=click.IntRange(1, 10))
@click.option("--replay-value", required=True, type=click.IntRange(1, 10))
@click.option("--notes", default="", help="What worked, what failed, and what to change next.")
@click.option("--scorebook", default="outputs/scores.json", show_default=True, help="Where to save cumulative scores.")
def score_version_command(
    artifact: str,
    version_label: str,
    emotion: int,
    yemeni_identity: int,
    vocal_beauty: int,
    lyrics: int,
    instrumental: int,
    replay_value: int,
    notes: str,
    scorebook: str,
) -> None:
    """Score a generated song version and update the running scorebook."""
    score = VersionScore(
        artifact_path=artifact,
        version_label=version_label,
        emotion=emotion,
        yemeni_identity=yemeni_identity,
        vocal_beauty=vocal_beauty,
        lyrics=lyrics,
        instrumental=instrumental,
        replay_value=replay_value,
        notes=notes,
    )
    scorebook_data = append_score(score, scorebook)
    click.echo(json.dumps(score.to_record(), ensure_ascii=False, indent=2))
    best = scorebook_data.get("best")
    if best:
        click.echo(f"Current best: {best['version_label']} with average {best['average']}")


@main.command("improve-prompt")
@click.option("--package", "package_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--scorebook", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "output_path", default="outputs/improved-package.json", show_default=True, type=click.Path(dir_okay=False))
def improve_prompt_command(package_path: str, scorebook: str, output_path: str) -> None:
    """Create a better package from the latest score feedback."""
    improved = improve_package(package_path=package_path, scorebook_path=scorebook, output_path=output_path)
    source = improved.get("improvement_source", {})
    click.echo(f"Wrote improved package: {output_path}")
    click.echo(json.dumps(source, ensure_ascii=False, indent=2))


def _read_text_input(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise click.ClickException("Input file is empty. Add lyrics, a song summary, or vibe notes first.")
    return text


def _write_package(data: dict, output_path: str) -> None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_package(package_path: str) -> dict:
    return json.loads(Path(package_path).read_text(encoding="utf-8"))


def _job_from_package(package_data: dict, output_dir: str, duration: int, bpm_hint: int | None = None) -> SongJob:
    prompt = package_data.get("music_prompt", "").strip()
    lyrics = package_data.get("lyric_adaptation_prompt", "").strip()

    if not prompt:
        raise click.ClickException("Package is missing music_prompt.")

    resolved_bpm_hint = bpm_hint if bpm_hint is not None else package_data.get("bpm_hint")
    return SongJob(
        prompt=prompt,
        lyrics=lyrics,
        output_dir=Path(output_dir),
        duration_seconds=duration,
        bpm_hint=resolved_bpm_hint,
    )


if __name__ == "__main__":
    main()
