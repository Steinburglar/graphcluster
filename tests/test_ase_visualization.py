# Date: 2026-03-24
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for ASE-backed visualization artifacts."""

from __future__ import annotations

from pathlib import Path

from ase.io import read

from graphcluster.analysis.lifecycle_report import ClusterLifecycleReport
from graphcluster.bundle.frame_bundle import FrameBundle
from graphcluster.graph.sparse_graph import SparseWeightedGraph
from graphcluster.partitioning.partition import Partition
from graphcluster.runner import TrajectoryPartitionRunner
from graphcluster.visualization.ase_viewer import payload_to_ase_atoms
from graphcluster.visualization.payload import VisualizationPayload
from graphcluster.visualization.visualizer import Visualizer
from graphcluster.io.frame import Frame


def test_payload_to_ase_atoms_keeps_debug_arrays() -> None:
    payload = VisualizationPayload(
        frame_index=3,
        positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        box=[[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 5.0]],
        cell_origin=[-1.0, -1.0, -1.0],
        atom_types=[1, 2],
        chemical_symbols=["Ga", "Pt"],
        labels=[7, 9],
        local_labels=[3, 4],
    )
    atoms = payload_to_ase_atoms(payload)
    assert len(atoms) == 2
    assert atoms.get_chemical_symbols() == ["Ga", "Pt"]
    assert atoms.get_positions().tolist() == [[1.0, 1.0, 1.0], [2.0, 1.0, 1.0]]
    assert atoms.arrays["cluster_label"].tolist() == [7, 9]
    assert atoms.arrays["cluster_color_code"].tolist() == [4972, 9242]
    assert atoms.arrays["local_cluster_label"].tolist() == [3, 4]
    assert atoms.arrays["raw_atom_type"].tolist() == [1, 2]
    assert "tags" not in atoms.arrays
    assert atoms.info["cell_origin"] == [-1.0, -1.0, -1.0]


def test_visualizer_writes_ase_trajectory_artifact(tmp_path: Path) -> None:
    visualizer = Visualizer.from_config(
        {
            "artifacts": {
                "visualization": {
                    "enabled": True,
                    "backend": "ase",
                    "mode": "traj",
                    "output_path": str(tmp_path / "visualization.extxyz"),
                }
            }
        }
    )
    bundle = FrameBundle(
        frame=Frame(
            index=1,
            positions=[[0.0, 0.0, 0.0]],
            atom_types=[2],
            chemical_symbols=["Pt"],
        ),
        graph=SparseWeightedGraph(frame_index=1, metadata={"num_nodes": 1}),
        partition=Partition(frame_index=1, labels=[5], kind="tracked"),
        local_partition=Partition(frame_index=1, labels=[0], kind="local"),
    )
    visualizer.consume(bundle)
    visualizer.finalize()

    artifact_path = tmp_path / "visualization.extxyz"
    assert artifact_path.exists()
    frames = read(str(artifact_path), index=":")
    assert len(frames) == 1
    assert frames[0].get_chemical_symbols() == ["Pt"]
    assert frames[0].arrays["cluster_label"].tolist() == [5]
    assert "cluster_color_code" in frames[0].arrays
    assert "tags" not in frames[0].arrays
    assert "chemical_symbols" not in frames[0].info


def test_pipeline_can_run_analysis_and_write_visualization(
    tmp_path: Path,
    default_toy_dataset: Path,
) -> None:
    artifact_path = tmp_path / "debug_visualization.extxyz"
    report_path = tmp_path / "cluster_lifecycle_report.jsonl"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source:",
                f"  path: {default_toy_dataset}",
                "  type_map:",
                "    1: Ga",
                "    2: Pt",
                "selection:",
                "  start: 0",
                "  stop: 2",
                "  stride: 1",
                "edges:",
                "  kind: distance",
                "  cutoff: 3.5",
                "partition:",
                "  algorithm: leiden",
                "  warm_start: true",
                "artifacts:",
                "  visualization:",
                "    enabled: true",
                "    backend: ase",
                "    mode: traj",
                f"    output_path: {artifact_path}",
                "  lifecycle_report:",
                "    enabled: true",
                f"    output_path: {report_path}",
            ]
        ),
        encoding="utf-8",
    )

    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(collect_bundles=True)
    assert result.frames_processed == 2
    for bundle in result.collected_bundles:
        assert len(bundle.partition.labels) == bundle.frame.metadata["num_atoms"]

    report = ClusterLifecycleReport.from_path(report_path)
    assert report.summary["num_frames"] == 2
    assert artifact_path.exists()
    assert report_path.exists()

    frames = read(str(artifact_path), index=":")
    assert len(frames) == 2
    assert set(frames[0].get_chemical_symbols()) == {"Ga", "Pt"}
    assert frames[0].arrays["cluster_label"].shape[0] == 129
    assert list(frames[0].info["cell_origin"]) == [-29.0, -29.0, -29.0]
    assert len(report.get_frame_cluster_counts()) == 2
