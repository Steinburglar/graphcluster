# Date: 2026-05-13
"""Tests for raw Allegro pre-energy and reconstructed model-energy tracking."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pytest

from graphcluster.analysis.cluster_energy import (
    compute_cluster_raw_allegro_energies,
    compute_cluster_reconstructed_model_energies,
)
from graphcluster.analysis.lifecycle_recorder import ClusterLifecycleRecorder
from graphcluster.analysis.lifecycle_report import ClusterLifecycleReport
from graphcluster.bundle.frame_bundle import FrameBundle
from graphcluster.graph.sparse_graph import SparseWeightedGraph
from graphcluster.io.frame import Frame
from graphcluster.partitioning.partition import Partition


matplotlib.use("Agg")


def test_compute_cluster_raw_allegro_energies_use_source_owned_signed_directed_terms() -> None:
    bundle = _build_bundle(
        labels=[0, 0, 1],
        edge_index=[[0, 1], [1, 0], [0, 2], [2, 0], [1, 2]],
        edge_energy=[-1.0, -0.5, 0.25, -0.75, 1.5],
        chemical_symbols=["H", "H", "Pt"],
    )

    cluster_records = compute_cluster_raw_allegro_energies(bundle)

    assert cluster_records == [
        {
            "cluster_id": 0,
            "size": 2,
            "energy_kind": "raw_pre_energy",
            "internal_energy": -1.5,
            "external_energy": 1.75,
            "combined_energy": 0.25,
            "internal_energy_per_atom": -0.75,
            "external_energy_per_atom": 0.875,
            "combined_energy_per_atom": 0.125,
        },
        {
            "cluster_id": 1,
            "size": 1,
            "energy_kind": "raw_pre_energy",
            "internal_energy": 0.0,
            "external_energy": -0.75,
            "combined_energy": -0.75,
            "internal_energy_per_atom": 0.0,
            "external_energy_per_atom": -0.75,
            "combined_energy_per_atom": -0.75,
        },
    ]


def test_compute_cluster_reconstructed_model_energies_use_source_owner_scale_shift() -> None:
    bundle = _build_bundle(
        labels=[0, 0, 1],
        edge_index=[[0, 1], [1, 2], [2, 1]],
        edge_energy=[8.0, 4.0, 12.0],
        chemical_symbols=["H", "H", "Pt"],
    )

    cluster_records = compute_cluster_reconstructed_model_energies(
        bundle,
        species_scales={"H": 10.0, "Pt": 100.0},
        species_shifts={"H": 1.0, "Pt": 2.0},
        avg_num_neighbors=8.0,
    )

    assert cluster_records == [
        {
            "cluster_id": 0,
            "size": 2,
            "energy_kind": "reconstructed_model_energy",
            "internal_model_energy": pytest.approx(20.0),
            "external_model_energy": pytest.approx(10.0),
            "shift_energy": pytest.approx(2.0),
            "combined_model_energy": pytest.approx(32.0),
            "internal_model_energy_per_atom": pytest.approx(10.0),
            "external_model_energy_per_atom": pytest.approx(5.0),
            "shift_energy_per_atom": pytest.approx(1.0),
            "combined_model_energy_per_atom": pytest.approx(16.0),
        },
        {
            "cluster_id": 1,
            "size": 1,
            "energy_kind": "reconstructed_model_energy",
            "internal_model_energy": pytest.approx(0.0),
            "external_model_energy": pytest.approx(300.0),
            "shift_energy": pytest.approx(2.0),
            "combined_model_energy": pytest.approx(302.0),
            "internal_model_energy_per_atom": pytest.approx(0.0),
            "external_model_energy_per_atom": pytest.approx(300.0),
            "shift_energy_per_atom": pytest.approx(2.0),
            "combined_model_energy_per_atom": pytest.approx(302.0),
        },
    ]


def test_lifecycle_recorder_writes_cluster_energy_even_for_non_allegro_clustering(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "cluster_lifecycle_report.jsonl"
    recorder = ClusterLifecycleRecorder.from_config(
        {
            "artifacts": {
                "lifecycle_report": {
                    "enabled": True,
                    "output_path": str(report_path),
                    "cluster_energy": {
                        "enabled": True,
                        "model_energy_reconstruction": {
                            "enabled": True,
                            "species_scales": {"H": 10.0, "Pt": 100.0},
                            "species_shifts": {"H": 1.0, "Pt": 2.0},
                            "avg_num_neighbors": 8.0,
                        },
                    },
                }
            }
        }
    )
    bundle = _build_bundle(
        labels=[0, 0, 1],
        edge_index=[[0, 1], [1, 0], [0, 2]],
        edge_energy=[-1.0, -0.5, 0.25],
        graph_metadata={"edge_kind": "gaussian", "num_nodes": 3},
        chemical_symbols=["H", "H", "Pt"],
    )

    recorder.consume(bundle)
    artifact_path = recorder.finalize()
    assert artifact_path == report_path

    report = ClusterLifecycleReport.from_path(report_path)
    assert report.has_cluster_energy() is True
    frame_energy = report.get_frame_cluster_energies()
    assert frame_energy[0]["cluster_energy"]["source"] == "allegro_raw"
    assert frame_energy[0]["cluster_energy"]["clusters"][0]["internal_energy"] == pytest.approx(-1.5)
    assert (
        frame_energy[0]["cluster_energy"]["clusters"][0]["internal_energy_per_atom"]
        == pytest.approx(-0.75)
    )
    assert (
        frame_energy[0]["cluster_energy"]["clusters"][0]["internal_model_energy"]
        == pytest.approx(-3.75)
    )
    assert (
        frame_energy[0]["cluster_energy"]["clusters"][0]["shift_energy"]
        == pytest.approx(2.0)
    )
    assert (
        frame_energy[0]["cluster_energy"]["clusters"][1]["shift_energy"]
        == pytest.approx(2.0)
    )


def test_lifecycle_recorder_fails_clearly_when_cluster_energy_requested_but_missing(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "cluster_lifecycle_report.jsonl"
    recorder = ClusterLifecycleRecorder.from_config(
        {
            "artifacts": {
                "lifecycle_report": {
                    "enabled": True,
                    "output_path": str(report_path),
                    "cluster_energy": {"enabled": True},
                }
            }
        }
    )
    bundle = FrameBundle(
        frame=Frame(index=0, positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], metadata={}),
        graph=SparseWeightedGraph(frame_index=0, metadata={"num_nodes": 2}),
        partition=Partition(frame_index=0, labels=[0, 1], kind="tracked", metadata={}),
        local_partition=Partition(frame_index=0, labels=[0, 1], kind="local"),
    )

    with pytest.raises(ValueError, match="Raw Allegro cluster energy tracking requires"):
        recorder.consume(bundle)


def test_lifecycle_report_exposes_cluster_energy_helpers(tmp_path: Path) -> None:
    artifact_path = tmp_path / "cluster_lifecycle_report.jsonl"
    records = [
        {
            "record_type": "header",
            "format": "graphcluster.cluster_lifecycle_report",
            "version": 1,
        },
        {
            "record_type": "frame",
            "frame_index": 0,
            "num_clusters": 1,
            "num_changed_atoms": 0,
            "tracking": {"births": [0], "deaths": [], "splits": [], "merges": [], "matches": []},
            "cluster_energy": {
                "source": "allegro_raw",
                "directed": True,
                "clusters": [
                    {
                        "cluster_id": 0,
                        "size": 2,
                        "energy_kind": "raw_pre_energy",
                        "internal_energy": -1.0,
                        "external_energy": 0.5,
                        "combined_energy": -0.5,
                        "internal_energy_per_atom": -0.5,
                        "external_energy_per_atom": 0.25,
                        "combined_energy_per_atom": -0.25,
                    }
                ],
                "model_energy_reconstruction": {
                    "enabled": True,
                    "source_atom_owns_edge": True,
                    "clusters": [
                        {
                            "cluster_id": 0,
                            "size": 2,
                            "energy_kind": "reconstructed_model_energy",
                            "internal_model_energy": -4.0,
                            "external_model_energy": -2.5,
                            "shift_energy": 3.0,
                            "combined_model_energy": -3.5,
                            "internal_model_energy_per_atom": -2.0,
                            "external_model_energy_per_atom": -1.25,
                            "shift_energy_per_atom": 1.5,
                            "combined_model_energy_per_atom": -1.75,
                        }
                    ],
                },
            },
        },
        {
            "record_type": "frame",
            "frame_index": 1,
            "num_clusters": 1,
            "num_changed_atoms": 0,
            "tracking": {"births": [], "deaths": [], "splits": [], "merges": [], "matches": []},
            "cluster_energy": {
                "source": "allegro_raw",
                "directed": True,
                "clusters": [
                    {
                        "cluster_id": 0,
                        "size": 2,
                        "energy_kind": "raw_pre_energy",
                        "internal_energy": -2.0,
                        "external_energy": 0.25,
                        "combined_energy": -1.75,
                        "internal_energy_per_atom": -1.0,
                        "external_energy_per_atom": 0.125,
                        "combined_energy_per_atom": -0.875,
                    }
                ],
                "model_energy_reconstruction": {
                    "enabled": True,
                    "source_atom_owns_edge": True,
                    "clusters": [
                        {
                            "cluster_id": 0,
                            "size": 2,
                            "energy_kind": "reconstructed_model_energy",
                            "internal_model_energy": -5.0,
                            "external_model_energy": -2.75,
                            "shift_energy": 3.0,
                            "combined_model_energy": -4.75,
                            "internal_model_energy_per_atom": -2.5,
                            "external_model_energy_per_atom": -1.375,
                            "shift_energy_per_atom": 1.5,
                            "combined_model_energy_per_atom": -2.375,
                        }
                    ],
                },
            },
        },
        {
            "record_type": "summary",
            "summary": {"num_frames": 2, "num_atoms": 2},
            "atom_switch_counts": [0, 0],
            "cluster_lifetimes": [
                {"cluster_id": 0, "first_seen_frame": 0, "last_seen_frame": 1, "frames_observed": 2}
            ],
        },
    ]
    with artifact_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")

    report = ClusterLifecycleReport.from_path(artifact_path)
    timeseries = report.get_cluster_energy_timeseries(0)

    assert report.has_cluster_energy() is True
    assert [record["frame_index"] for record in timeseries] == [0, 1]
    assert timeseries[1]["combined_energy"] == pytest.approx(-1.75)
    assert timeseries[1]["combined_energy_per_atom"] == pytest.approx(-0.875)
    assert timeseries[1]["combined_model_energy"] == pytest.approx(-4.75)

    fig, axes = report.plot_cluster_energy_timeseries(
        0,
        components=("internal_model_energy", "shift_energy"),
    )
    assert len(axes) == 2
    assert axes[0].get_title() == "Tracked cluster 0 internal_model_energy"
    assert axes[1].get_title() == "Tracked cluster 0 shift_energy"
    fig.clf()


def test_lifecycle_report_backfills_per_atom_fields_for_older_artifacts(tmp_path: Path) -> None:
    artifact_path = tmp_path / "cluster_lifecycle_report.jsonl"
    records = [
        {
            "record_type": "header",
            "format": "graphcluster.cluster_lifecycle_report",
            "version": 1,
        },
        {
            "record_type": "frame",
            "frame_index": 0,
            "num_clusters": 1,
            "num_changed_atoms": 0,
            "tracking": {"births": [0], "deaths": [], "splits": [], "merges": [], "matches": []},
            "cluster_energy": {
                "source": "allegro_raw",
                "directed": True,
                "clusters": [
                    {
                        "cluster_id": 0,
                        "size": 4,
                        "internal_energy": -20.0,
                        "external_energy": -4.0,
                        "combined_energy": -24.0,
                    }
                ],
            },
        },
        {
            "record_type": "summary",
            "summary": {"num_frames": 1, "num_atoms": 4},
            "atom_switch_counts": [0, 0, 0, 0],
            "cluster_lifetimes": [
                {"cluster_id": 0, "first_seen_frame": 0, "last_seen_frame": 0, "frames_observed": 1}
            ],
        },
    ]
    with artifact_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")

    report = ClusterLifecycleReport.from_path(artifact_path)
    timeseries = report.get_cluster_energy_timeseries(0)
    frame_energy = report.get_frame_cluster_energies()

    assert timeseries[0]["internal_energy_per_atom"] == pytest.approx(-5.0)
    assert timeseries[0]["external_energy_per_atom"] == pytest.approx(-1.0)
    assert timeseries[0]["combined_energy_per_atom"] == pytest.approx(-6.0)
    assert frame_energy[0]["cluster_energy"]["clusters"][0]["combined_energy_per_atom"] == pytest.approx(-6.0)


def _build_bundle(
    *,
    labels: list[int],
    edge_index: list[list[int]],
    edge_energy: list[float],
    graph_metadata: dict | None = None,
    chemical_symbols: list[str] | None = None,
) -> FrameBundle:
    num_nodes = len(labels)
    metadata = {
        "allegro_edge_indices": edge_index,
        "allegro_edge_energies": edge_energy,
    }
    return FrameBundle(
        frame=Frame(
            index=0,
            positions=[[float(index), 0.0, 0.0] for index in range(num_nodes)],
            chemical_symbols=chemical_symbols,
            metadata=metadata,
        ),
        graph=SparseWeightedGraph(
            frame_index=0,
            metadata={"num_nodes": num_nodes, **(graph_metadata or {})},
        ),
        partition=Partition(frame_index=0, labels=list(labels), kind="tracked", metadata={}),
        local_partition=Partition(frame_index=0, labels=list(labels), kind="local"),
    )
