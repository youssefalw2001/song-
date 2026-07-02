from __future__ import annotations

import json
from pathlib import Path

import click

from song_lab.pipeline import build_conversion_package
from song_lab.presets import STYLE_PRESETS


@click.command()
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
def main(input_path: str, style: str, output_path: str) -> None:
    """Create a repeatable test package for Yemeni-style song conversion."""
    source_text = Path(input_path).read_text(encoding="utf-8").strip()
    if not source_text:
        raise click.ClickException("Input file is empty. Add lyrics, a song summary, or vibe notes first.")

    package = build_conversion_package(source_text=source_text, style_key=style)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(package.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(f"Wrote conversion test package: {destination}")
    click.echo("Next: paste the music_prompt + lyric_adaptation_prompt output into your music generator and score the result.")


if __name__ == "__main__":
    main()
