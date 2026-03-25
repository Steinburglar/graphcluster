# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for trajectory-level lifecycle analysis.

These tests focus on the separation between online tracking and later
trajectory-level summary analysis.
"""

import json
from pathlib import Path

from graphcluster.analysis.cluster_lifecycle_analyzer import ClusterLifecycleAnalyzer
from graphcluster.analysis.lifecycle_report import ClusterLifecycleReport
from graphcluster.partitioning.partition import Partition
from graphcluster.partitioning.partition_trajectory import PartitionTrajectory


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
