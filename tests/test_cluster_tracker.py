# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for online frame-to-frame synchronization.

These tests protect the intended meaning of tracking: it should be a forward
pass synchronization step, not a whole-trajectory analysis pass.
"""

from graphcluster.partitioning.partition import Partition
from graphcluster.tracking.cluster_tracker import ClusterTracker


def test_tracker_returns_tracked_partition() -> None:
    tracker = ClusterTracker.from_config({})
    tracked = tracker.synchronize(Partition(frame_index=0, labels=[0, 0], kind="local"))
    assert tracked.kind == "tracked"


def test_tracker_remembers_previous_tracked_partition() -> None:
    tracker = ClusterTracker.from_config({})
    first = tracker.synchronize(Partition(frame_index=0, labels=[0], kind="local"))
    second = tracker.synchronize(Partition(frame_index=1, labels=[1], kind="local"))
    assert tracker.previous_partition() == second
    assert first.frame_index == 0
