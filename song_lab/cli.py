from __future__ import annotations

import json
from pathlib import Path

import click

from song_lab.audio.jobs import SongJob
from song_lab.pipeline import build_conversion_package
from song_lab.presets import STYLE_PRESETS
from song_lab.providers.ace_step_api import AceStepApiProvider
from song_lab.providers.mock import MockSongProvider


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
    source_text = Path(input_path).read_text(encoding="utf-8").strip()
    if not source_text:
        raise click.ClickException("Input file is empty. Add lyrics, a song summary, or vibe notes first.")

    package = build_conversion_package(source_text=source_text, style_key=style)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(package.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"Wrote conversion test package: {destination}")
    click.echo("Next: run mock-audio or ace-audio to generate an artifact.")


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
def ace_audio_command(
    package_path: str,
    output_dir: str,
    base_url: str,
    api_key: str | None,
    model: str,
    duration: int,
    audio_format: str,
    vocal_language: str,
) -> None:
    """Generate real audio using a running ACE-Step API server."""
    package_data = _read_package(package_path)
    provider = AceStepApiProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        audio_format=audio_format,
        vocal_language=vocal_language,
    )
    result = provider.run(_job_from_package(package_data, output_dir, duration))
    click.echo(result.model_dump_json(indent=2))


def _read_package(package_path: str) -> dict:
    return json.loads(Path(package_path).read_text(encoding="utf-8"))


def _job_from_package(package_data: dict, output_dir: str, duration: int) -> SongJob:
    prompt = package_data.get("music_prompt", "").strip()
    lyrics = package_data.get("lyric_adaptation_prompt", "").strip()

    if not prompt:
        raise click.ClickException("Package is missing music_prompt.")

    return SongJob(
        prompt=prompt,
        lyrics=lyrics,
        output_dir=Path(output_dir),
        duration_seconds=duration,
    )


if __name__ == "__main__":
    main()
