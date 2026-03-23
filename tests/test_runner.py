# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for the top-level runner loop.

These tests describe the shape of the forward pass over a trajectory and help
keep the orchestration logic simple as the project grows.
"""

from pathlib import Path

from graphcluster.runner import TrajectoryPartitionRunner


def test_runner_emits_one_bundle_per_frame(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input:",
                f"  trajectory: {default_toy_dataset}",
                "frames:",
                "  start: 0",
                "  stop: 3",
                "  stride: 1",
                "graph:",
                "  source: trajectory",
                "partition:",
                "  warm_start: true",
            ]
        ),
        encoding="utf-8",
    )
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    bundles = runner.run()
    assert len(bundles) == 3
    assert bundles[0].frame.index == 0
    assert set(bundles[0].frame.atom_types) == {1, 2}


def test_runner_uses_default_toy_dataset_from_fixture(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input:",
                f"  trajectory: {default_toy_dataset}",
                "frames:",
                "  start: 0",
                "  stop: 1",
                "  stride: 1",
            ]
        ),
        encoding="utf-8",
    )
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    assert runner.config["input"]["trajectory"] == str(default_toy_dataset)
