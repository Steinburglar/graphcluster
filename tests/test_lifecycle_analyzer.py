# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for trajectory-level lifecycle analysis.

These tests focus on the separation between online tracking and later
trajectory-level summary analysis.
"""

from graphcluster.analysis.cluster_lifecycle_analyzer import ClusterLifecycleAnalyzer
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
