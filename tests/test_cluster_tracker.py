# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for online frame-to-frame synchronization.

These tests protect the intended meaning of tracking: it should be a forward
pass synchronization step, not a whole-trajectory analysis pass.
"""

from graphcluster.partitioning.partition import Partition
from graphcluster.tracking.cluster_tracker import ClusterTracker
from graphcluster.tracking.metadata import TrackingFrameMetadata


def test_tracker_returns_tracked_partition() -> None:
    tracker = ClusterTracker.from_config({})
    tracked = tracker.synchronize(Partition(frame_index=0, labels=[0, 0], kind="local"))
    assert tracked.kind == "tracked"
    assert isinstance(tracked.metadata["tracking"], TrackingFrameMetadata)


def test_tracker_preserves_first_frame_local_labels_as_initial_tracked_labels() -> None:
    tracker = ClusterTracker.from_config({})
    tracked = tracker.synchronize(Partition(frame_index=0, labels=[7, 7, 3, 3], kind="local"))
    assert tracked.labels == [7, 7, 3, 3]
    tracking = tracked.metadata["tracking"]
    assert tracking.local_to_tracked == {7: 7, 3: 3}
    assert tracking.births == [3, 7]


def test_tracker_remembers_previous_tracked_partition() -> None:
    tracker = ClusterTracker.from_config({})
    first = tracker.synchronize(Partition(frame_index=0, labels=[0], kind="local"))
    second = tracker.synchronize(Partition(frame_index=1, labels=[1], kind="local"))
    assert tracker.previous_partition() == second
    assert first.frame_index == 0


def test_tracker_preserves_cluster_ids_when_local_labels_change() -> None:
    tracker = ClusterTracker.from_config({})
    first = tracker.synchronize(Partition(frame_index=0, labels=[0, 0, 1, 1], kind="local"))
    second = tracker.synchronize(Partition(frame_index=1, labels=[7, 7, 3, 3], kind="local"))

    assert first.labels == [0, 0, 1, 1]
    assert second.labels == [0, 0, 1, 1]
    tracking = second.metadata["tracking"]
    assert tracking.local_to_tracked == {7: 0, 3: 1}
    assert tracking.births == []
    assert tracking.deaths == []


def test_tracker_reports_split_as_birth_plus_split_metadata() -> None:
    tracker = ClusterTracker.from_config({"tracking": {"match_threshold": 0.5}})
    tracker.synchronize(Partition(frame_index=0, labels=[0, 0, 0, 0], kind="local"))
    second = tracker.synchronize(Partition(frame_index=1, labels=[5, 5, 6, 6], kind="local"))

    assert second.labels == [0, 0, 1, 1]
    tracking = second.metadata["tracking"]
    assert tracking.births == [1]
    assert tracking.deaths == []
    assert tracking.splits == {0: [0, 1]}
    assert tracking.merges == {}


def test_tracker_reports_merge_and_death_metadata() -> None:
    tracker = ClusterTracker.from_config({"tracking": {"match_threshold": 0.5}})
    tracker.synchronize(Partition(frame_index=0, labels=[0, 0, 1, 1], kind="local"))
    second = tracker.synchronize(Partition(frame_index=1, labels=[9, 9, 9, 9], kind="local"))

    assert len(set(second.labels)) == 1
    tracking = second.metadata["tracking"]
    tracked_label = second.labels[0]
    assert tracking.births == []
    assert tracking.deaths == [1]
    assert tracking.splits == {}
    assert tracking.merges == {tracked_label: [0, 1]}


def test_tracker_records_match_scores_and_uncertainty() -> None:
    tracker = ClusterTracker.from_config(
        {"tracking": {"overlap_metric": "jaccard", "match_threshold": 0.2}}
    )
    tracker.synchronize(Partition(frame_index=0, labels=[0, 0, 1, 1], kind="local"))
    second = tracker.synchronize(Partition(frame_index=1, labels=[2, 2, 2, 1], kind="local"))

    tracking = second.metadata["tracking"]
    match_by_local = {match.local_label: match for match in tracking.matches}
    assert match_by_local[2].previous_tracked_label == 0
    assert match_by_local[2].score > 0.0
    assert 0.0 <= match_by_local[2].confidence <= 1.0
    assert 0.0 <= match_by_local[2].uncertainty <= 1.0
