# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for the top-level runner loop.

These tests describe the shape of the forward pass over a trajectory and help
keep the orchestration logic simple as the project grows.
"""

from pathlib import Path

from ase import Atoms
from ase.io import write

from graphcluster.runner import TrajectoryPartitionRunner


def test_runner_emits_one_bundle_per_frame(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {default_toy_dataset}",
                "selection:",
                "  start: 0",
                "  stop: 3",
                "  stride: 1",
                "edges:",
                "  kind: binary",
                "  cutoff: 3.5",
                "partition:",
                "  algorithm: leiden",
                "  warm_start: true",
            ]
        ),
        encoding="utf-8",
    )
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(collect_bundles=True)
    bundles = result.collected_bundles
    assert result.frames_processed == 3
    assert len(bundles) == 3
    assert bundles[0].frame.index == 0
    assert set(bundles[0].frame.atom_types) == {1, 2}
    assert len(bundles[0].partition.labels) == bundles[0].frame.metadata["num_atoms"]
    assert bundles[0].graph.metadata["num_edges"] > 0


def test_runner_writes_report_artifact_without_collecting_bundles(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    report_path = tmp_path / "cluster_lifecycle_report.jsonl"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {default_toy_dataset}",
                "selection:",
                "  start: 0",
                "  stop: 2",
                "  stride: 1",
                "edges:",
                "  kind: binary",
                "  cutoff: 3.5",
                "partition:",
                "  algorithm: leiden",
                "artifacts:",
                "  lifecycle_report:",
                "    enabled: true",
                f"    output_path: {report_path}",
            ]
        ),
        encoding="utf-8",
    )
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run()
    assert result.frames_processed == 2
    assert result.collected_bundles == []
    assert result.analysis_artifact == report_path
    assert report_path.exists()


def test_runner_uses_default_toy_dataset_from_fixture(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {default_toy_dataset}",
                "selection:",
                "  start: 0",
                "  stop: 1",
                "  stride: 1",
                "edges:",
                "  kind: binary",
                "  cutoff: 3.5",
                "partition:",
                "  algorithm: leiden",
            ]
        ),
        encoding="utf-8",
    )
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    assert runner.config["source"]["path"] == str(default_toy_dataset)


def test_runner_can_process_xyz_trajectory(tmp_path: Path) -> None:
    xyz_path = tmp_path / "toy.xyz"
    xyz_path.write_text(
        "\n".join(
            [
                "2",
                "frame 0",
                "Si 0.0 0.0 0.0",
                "O 1.0 0.0 0.0",
                "2",
                "frame 1",
                "Si 0.1 0.0 0.0",
                "O 1.1 0.0 0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                "  backend: ase",
                "  format: xyz",
                f"  path: {xyz_path}",
                "selection:",
                "  start: 0",
                "  stop: 2",
                "  stride: 1",
                "edges:",
                "  kind: binary",
                "  cutoff: 1.5",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.05",
            ]
        ),
        encoding="utf-8",
    )

    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(collect_bundles=True)
    bundles = result.collected_bundles
    assert result.frames_processed == 2
    assert len(bundles) == 2
    assert bundles[0].frame.atom_types == ["Si", "O"]
    assert bundles[0].frame.chemical_symbols == ["Si", "O"]
    assert len(bundles[0].partition.labels) == 2


def test_runner_can_emit_progress_messages(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {default_toy_dataset}",
                "selection:",
                "  start: 0",
                "  stop: 2",
                "  stride: 1",
                "edges:",
                "  kind: binary",
                "  cutoff: 3.5",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.05",
            ]
        ),
        encoding="utf-8",
    )

    messages: list[str] = []
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(progress=True, progress_callback=messages.append)

    assert result.frames_processed == 2
    assert any(message.startswith("Starting graphcluster run:") for message in messages)
    assert any("Processed frame 0" in message for message in messages)
    assert any(message.startswith("Finished graphcluster run:") for message in messages)


def test_runner_can_emit_profiling_messages(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {default_toy_dataset}",
                "selection:",
                "  start: 0",
                "  stop: 1",
                "  stride: 1",
                "edges:",
                "  kind: binary",
                "  cutoff: 3.5",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.05",
            ]
        ),
        encoding="utf-8",
    )

    messages: list[str] = []
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(progress=True, progress_callback=messages.append, profile=True)

    assert result.frames_processed == 1
    assert result.startup_timings["startup_total"] >= 0.0
    assert result.run_timings["run_total"] >= 0.0
    assert any(message.startswith("Profiling startup:") for message in messages)
    assert any(message.startswith("Profiling runtime:") for message in messages)


def test_runner_can_process_preannotated_allegro_trajectory(tmp_path: Path) -> None:
    traj_path = tmp_path / "already_annotated.traj"
    atoms = Atoms("GaPt", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    atoms.info["allegro_edge_indices"] = [[0, 1], [1, 0]]
    atoms.info["allegro_edge_energies"] = [-0.2, -0.3]
    write(traj_path, atoms, format="traj")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {traj_path}",
                "selection:",
                "  start: 0",
                "  stop: 1",
                "  stride: 1",
                "edges:",
                "  kind: allegro",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.05",
            ]
        ),
        encoding="utf-8",
    )

    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(collect_bundles=True)

    assert result.frames_processed == 1
    assert result.collected_bundles[0].graph.metadata["source"] == "allegro"
    assert result.collected_bundles[0].graph.adjacency[0, 1] == 0.5


def test_runner_fails_clearly_when_allegro_source_is_not_annotated(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.traj"
    atoms = Atoms("GaPt", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    write(raw_path, atoms, format="traj")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {raw_path}",
                "selection:",
                "  start: 0",
                "  stop: 1",
                "  stride: 1",
                "edges:",
                "  kind: allegro",
                "partition:",
                "  algorithm: leiden",
            ]
        ),
        encoding="utf-8",
    )

    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    try:
        runner.run(collect_bundles=True)
    except ValueError as exc:
        assert "edges.kind='allegro'" in str(exc)
    else:
        raise AssertionError("Expected missing Allegro metadata to raise ValueError.")
