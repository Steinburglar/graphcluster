# Date: 2026-04-01
"""Tests for the toy proton-transfer experiment scaffolding."""

from pathlib import Path
import sys

from ase.io import read, write

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from water.proton_transfer import analyze_proton_transfer_bundles, write_proton_transfer_outputs
from water.toy_proton_water import (
    ToyProtonTrajectorySpec,
    generate_toy_proton_transfer_trajectory,
)
from graphcluster.io.trajectory_reader import TrajectoryReader
from graphcluster.runner import TrajectoryPartitionRunner


def test_toy_proton_trajectory_contains_expected_metadata(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "toy_proton_water.traj"
    summary = generate_toy_proton_transfer_trajectory(
        trajectory_path,
        spec=ToyProtonTrajectorySpec(num_frames=24, cycle_length=12),
    )

    reader = TrajectoryReader(
        trajectory_path=str(trajectory_path),
        format="traj",
    )
    frames = list(reader)

    assert summary["num_frames"] == 24
    assert len(frames) == 24
    assert len(frames[0].positions) == 13
    assert frames[0].chemical_symbols == ["O", "O", "O", "O"] + ["H"] * 9
    assert frames[0].metadata["ase_info"]["toy_shared_proton_index"] == 12
    assignments = [frame.metadata["ase_info"]["toy_target_assignment"] for frame in frames]
    assert len(set(assignments)) == 2


def test_toy_proton_analysis_runs_end_to_end(tmp_path: Path) -> None:
    trajectory_path = tmp_path / "toy_proton_water.traj"
    generate_toy_proton_transfer_trajectory(
        trajectory_path,
        spec=ToyProtonTrajectorySpec(num_frames=24, cycle_length=12),
    )

    config_path = tmp_path / "toy_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                "  backend: ase",
                "  format: traj",
                f"  path: {trajectory_path}",
                "selection:",
                "  start: 0",
                "  stop: 24",
                "  stride: 1",
                "edges:",
                "  kind: gaussian",
                "  cutoff: 2.6",
                "  sigma: 0.7",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.08",
                "  warm_start: true",
                "artifacts:",
                "  visualization:",
                "    enabled: false",
                "  lifecycle_report:",
                "    enabled: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    run_result = runner.run(collect_bundles=True)
    analysis = analyze_proton_transfer_bundles(
        run_result.collected_bundles,
        persistence=2,
        event_window=3,
    )
    output_paths = write_proton_transfer_outputs(analysis, tmp_path / "analysis")

    assert run_result.frames_processed == 24
    assert len(analysis.per_frame_rows) == 24
    assert analysis.summary["num_detected_hops"] >= 1
    assert all(row["community_size"] >= 1 for row in analysis.per_frame_rows)
    assert Path(output_paths["per_frame_csv"]).exists()
    assert Path(output_paths["summary_json"]).exists()


def test_toy_proton_analysis_can_run_on_allegro_annotated_toy_trajectory(
    tmp_path: Path,
) -> None:
    raw_trajectory_path = tmp_path / "toy_proton_water.traj"
    annotated_trajectory_path = tmp_path / "toy_proton_water_allegro.traj"
    generate_toy_proton_transfer_trajectory(
        raw_trajectory_path,
        spec=ToyProtonTrajectorySpec(num_frames=18, cycle_length=9),
    )
    frames = read(raw_trajectory_path, index=":", format="traj")
    for atoms in frames:
        proton_index = int(atoms.info["toy_shared_proton_index"])
        donor_index = int(atoms.info["toy_donor_oxygen_index"])
        acceptor_index = int(atoms.info["toy_acceptor_oxygen_index"])
        atoms.info["allegro_edge_indices"] = [
            [proton_index, donor_index],
            [donor_index, proton_index],
            [proton_index, acceptor_index],
            [acceptor_index, proton_index],
        ]
        atoms.info["allegro_edge_energies"] = [-1.2, -1.0, -0.6, -0.5]
    write(annotated_trajectory_path, frames, format="traj")

    config_path = tmp_path / "toy_allegro_config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                "  backend: ase",
                "  format: traj",
                f"  path: {annotated_trajectory_path}",
                "selection:",
                "  start: 0",
                "  stop: 18",
                "  stride: 1",
                "edges:",
                "  kind: allegro",
                "  directed: false",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.08",
                "  warm_start: true",
                "artifacts:",
                "  visualization:",
                "    enabled: false",
                "  lifecycle_report:",
                "    enabled: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    run_result = runner.run(collect_bundles=True)
    analysis = analyze_proton_transfer_bundles(run_result.collected_bundles, persistence=2)

    assert run_result.frames_processed == 18
    assert len(analysis.per_frame_rows) == 18
    assert analysis.summary["assignment_accuracy"] == 1.0
    assert analysis.summary["num_detected_hops"] >= 1
