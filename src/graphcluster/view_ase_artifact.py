# Date: 2026-03-24
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Inspect or render ASE visualization artifacts produced by graphcluster."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for inspecting ASE artifacts."""
    parser = argparse.ArgumentParser(
        description="Inspect or render an ASE trajectory artifact written by graphcluster."
    )
    parser.add_argument("artifact", help="Path to an ASE-readable trajectory artifact.")
    parser.add_argument(
        "--frame",
        type=int,
        default=0,
        help="Frame index inside the artifact to inspect or render.",
    )
    parser.add_argument(
        "--mode",
        choices=["summary", "gui", "png"],
        default="summary",
        help="Whether to print a summary, open an ASE GUI, or save a PNG snapshot.",
    )
    parser.add_argument(
        "--output",
        help="Optional PNG output path when using --mode png.",
    )
    return parser


def main() -> None:
    """Entrypoint for the ASE artifact helper CLI."""
    parser = build_parser()
    args = parser.parse_args()
    artifact_path = Path(args.artifact)
    frames = _read_frames(artifact_path)
    if not frames:
        raise ValueError(f"No frames found in visualization artifact: {artifact_path}")
    if args.frame < 0 or args.frame >= len(frames):
        raise IndexError(
            f"Requested frame {args.frame}, but artifact contains {len(frames)} frames."
        )

    if args.mode == "summary":
        _print_summary(artifact_path, frames, args.frame)
        return
    if args.mode == "gui":
        from ase.visualize import view

        view(frames[args.frame])
        return

    output_path = Path(args.output) if args.output else artifact_path.with_suffix(".png")
    _write_png(frames[args.frame], output_path)
    print(output_path)


def _read_frames(artifact_path: Path) -> list:
    """Load all frames from an ASE-readable artifact."""
    from ase.io import read

    frames = read(str(artifact_path), index=":")
    if isinstance(frames, list):
        return frames
    return [frames]


def _print_summary(artifact_path: Path, frames: list, selected_frame: int) -> None:
    """Print a compact summary of a visualization artifact."""
    frame = frames[selected_frame]
    print(f"artifact: {artifact_path}")
    print(f"frames: {len(frames)}")
    print(f"selected_frame: {selected_frame}")
    print(f"num_atoms: {len(frame)}")
    print(f"arrays: {sorted(frame.arrays.keys())}")
    print(f"info_keys: {sorted(frame.info.keys())}")


def _write_png(atoms, output_path: Path) -> None:
    """Save one frame as a simple PNG snapshot."""
    try:
        import matplotlib.pyplot as plt
        from ase.visualize.plot import plot_atoms
    except ImportError as exc:
        raise RuntimeError(
            "PNG export requires matplotlib. Install graphcluster with the 'vis' "
            "extra or add matplotlib to the environment."
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    plot_atoms(atoms, ax, radii=0.3, rotation=("0x,0y,0z"))
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
