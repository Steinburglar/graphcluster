# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for trajectory-level lifecycle analysis.

These tests focus on the separation between online tracking and later
trajectory-level summary analysis.
"""

import json
from pathlib import Path

import matplotlib

from graphcluster.analysis.cluster_lifecycle_analyzer import ClusterLifecycleAnalyzer
from graphcluster.analysis.lifecycle_report import ClusterLifecycleReport
from graphcluster.partitioning.partition import Partition
from graphcluster.partitioning.partition_trajectory import PartitionTrajectory


matplotlib.use("Agg")


def test_lifecycle_analyzer_reports_partition_count() -> None:
    trajectory = PartitionTrajectory(
        partitions=[
            Partition(frame_index=0, labels=[0], kind="tracked"),
            Partition(frame_index=1, labels=[0], kind="tracked"),
        ]
    )
    report = ClusterLifecycleAnalyzer().analyze(trajectory)
    assert report.summary["num_partitions"] == 2


def test_lifecycle_report_can_be_loaded_from_artifact(tmp_path: Path) -> None:
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
            "num_clusters": 2,
            "num_changed_atoms": 0,
            "tracking": {
                "births": [0, 1],
                "deaths": [],
                "splits": [],
                "merges": [],
                "matches": [],
            },
        },
        {
            "record_type": "summary",
            "summary": {"num_frames": 1, "num_atoms": 4},
            "atom_switch_counts": [0, 1, 0, 2],
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
    assert report.summary["num_frames"] == 1
    assert report.get_births() == [{"frame_index": 0, "cluster_ids": [0, 1]}]
    assert report.get_atom_switch_counts() == [0, 1, 0, 2]


def test_lifecycle_report_exposes_activity_and_plot_helpers(tmp_path: Path) -> None:
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
            "num_clusters": 2,
            "num_changed_atoms": 0,
            "tracking": {
                "births": [0, 1],
                "deaths": [],
                "splits": [],
                "merges": [],
                "matches": [],
            },
        },
        {
            "record_type": "frame",
            "frame_index": 1,
            "num_clusters": 3,
            "num_changed_atoms": 2,
            "tracking": {
                "births": [2],
                "deaths": [1],
                "splits": [{"previous_cluster_id": 0, "current_cluster_ids": [0, 2]}],
                "merges": [{"current_cluster_id": 2, "previous_cluster_ids": [0, 1]}],
                "matches": [],
            },
        },
        {
            "record_type": "summary",
            "summary": {
                "num_frames": 2,
                "num_atoms": 4,
                "total_births": 3,
                "total_deaths": 1,
                "total_splits": 1,
                "total_merges": 1,
            },
            "atom_switch_counts": [0, 3, 1, 3],
            "cluster_lifetimes": [
                {"cluster_id": 0, "first_seen_frame": 0, "last_seen_frame": 1, "frames_observed": 2},
                {"cluster_id": 2, "first_seen_frame": 1, "last_seen_frame": 1, "frames_observed": 1},
            ],
        },
    ]
    with artifact_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")

    report = ClusterLifecycleReport.from_path(artifact_path)

    assert report.get_summary_table()["num_frames"] == 2
    assert report.get_event_counts() == {
        "total_births": 3,
        "total_deaths": 1,
        "total_splits": 1,
        "total_merges": 1,
    }
    assert report.get_num_active_atoms(min_switches=1) == 3
    assert report.get_top_atoms_by_switches(2) == [
        {"atom_index": 1, "switch_count": 3},
        {"atom_index": 3, "switch_count": 3},
    ]
    assert report.get_longest_lived_clusters(1)[0]["cluster_id"] == 0

    fig_counts, axes = report.plot_cluster_count_timeseries()
    fig_switches, ax_switches = report.plot_atom_switch_histogram()
    fig_lifetimes, ax_lifetimes = report.plot_cluster_lifetime_histogram()

    assert len(axes) == 2
    assert ax_switches.get_title() == "Atom activity histogram"
    assert ax_lifetimes.get_title() == "Tracked-cluster lifetime histogram"

    fig_counts.clf()
    fig_switches.clf()
    fig_lifetimes.clf()
