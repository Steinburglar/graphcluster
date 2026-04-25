# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Command-line entrypoint for graphcluster.

This file is the human-facing shell around the package. It should stay thin:
it parses user input and hands control to the runner.

Who touches this:
- people adding CLI flags or subcommands

Who this touches:
- the configuration loader
- the top-level trajectory runner
"""

from __future__ import annotations

import argparse

from .runner import TrajectoryPartitionRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the initial CLI parser."""
    parser = argparse.ArgumentParser(description="Run graph clustering on an MD trajectory.")
    parser.add_argument("config", help="Path to the YAML config file for the run.")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Emit startup and runtime timing summaries for the run.",
    )
    return parser


def main() -> None:
    """Entrypoint used by the console script."""
    parser = build_parser()
    args = parser.parse_args()
    runner = TrajectoryPartitionRunner.from_config_path(args.config)
    runner.run(progress=True, profile=args.profile)
