"""Standalone CLI for exporting Allegro edge annotations.

This command is intentionally separate from ``graphcluster``. It turns a raw
ASE-readable trajectory into an annotated trajectory artifact that downstream
analysis can consume as a normal input file.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> None:
    """Run the ``annotate-allegro`` command."""
    args = build_parser().parse_args(argv)
    output_path = annotate_from_args(args)
    print(f"Finished Allegro edge annotation: output={output_path}")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="annotate-allegro",
        description="Export Allegro edge energies onto an ASE-readable trajectory.",
    )
    parser.add_argument("--input", required=True, help="Raw source trajectory path.")
    parser.add_argument("--compiled-model", required=True, help="Compiled Allegro model path.")
    parser.add_argument("--output", required=True, help="Annotated output trajectory path.")
    parser.add_argument("--input-format", default=None, help="ASE input format override.")
    parser.add_argument("--output-format", default=None, help="ASE output format override.")
    parser.add_argument("--device", default="cpu", help="Torch device for annotation.")
    parser.add_argument("--start", type=int, default=0, help="First frame index.")
    parser.add_argument("--stop", type=int, default=None, help="Exclusive stop frame index.")
    parser.add_argument("--stride", type=int, default=1, help="Frame stride.")
    parser.add_argument(
        "--raw-type-map",
        action="append",
        default=[],
        metavar="RAW=SYMBOL",
        help="Map raw source atom type to chemical symbol. May be repeated.",
    )
    parser.add_argument(
        "--species-to-model-type-map",
        action="append",
        default=[],
        metavar="SYMBOL=MODEL_TYPE",
        help="Map chemical species to model atom type. May be repeated.",
    )
    return parser


def annotate_from_args(
    args: argparse.Namespace,
    *,
    annotate_trajectory_fn: Callable[..., str | Path] | None = None,
) -> Path:
    """Run annotation from parsed args and return the output path."""
    if annotate_trajectory_fn is None:
        from allegro_ase_edge_export.annotate_trajectory import (
            annotate_trajectory as annotate_trajectory_fn,
        )

    raw_type_map = parse_key_value_args(args.raw_type_map)
    species_map_entries = parse_key_value_args(args.species_to_model_type_map)
    chemical_species_to_atom_type_map: dict[str, str] | bool
    chemical_species_to_atom_type_map = species_map_entries or True

    print(
        "Running Allegro edge annotation: "
        f"input={args.input}, output={args.output}, device={args.device}"
    )
    result = annotate_trajectory_fn(
        compiled_model=args.compiled_model,
        input_path=args.input,
        output_path=args.output,
        input_format=args.input_format,
        output_format=args.output_format,
        device=args.device,
        start=args.start,
        stop=args.stop,
        stride=args.stride,
        raw_type_map=raw_type_map,
        chemical_species_to_atom_type_map=chemical_species_to_atom_type_map,
    )
    return Path(result)


def parse_key_value_args(entries: Sequence[str]) -> dict[str, str]:
    """Parse repeated ``KEY=VALUE`` CLI arguments into a dict."""
    parsed: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Expected KEY=VALUE mapping, got {entry!r}.")
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"Expected non-empty KEY=VALUE mapping, got {entry!r}.")
        parsed[key] = value
    return parsed
