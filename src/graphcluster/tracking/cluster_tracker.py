# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Online frame-to-frame partition synchronization.

In intuitive terms, this class makes the current frame's cluster IDs line up
with the previous tracked frame. It is not responsible for trajectory-level
lifetime analysis.

Who touches this:
- the top-level runner
- people implementing temporal label synchronization

Who this touches:
- local partitions
- tracked partitions
- tracking state
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from scipy.optimize import linear_sum_assignment

from ..partitioning.partition import Partition
from .metadata import ClusterMatchRecord, TrackingFrameMetadata
from .tracking_state import TrackingState


@dataclass
class ClusterTracker:
    """Synchronize local partitions into tracked partitions."""

    config: dict
    state: TrackingState = field(default_factory=TrackingState)

    @classmethod
    def from_config(cls, config: dict) -> "ClusterTracker":
        """Build a tracker from config."""
        return cls(config=config)

    def previous_partition(self) -> Partition | None:
        """Return the previous tracked partition, if any."""
        return self.state.previous_tracked_partition

    def synchronize(self, local_partition: Partition) -> Partition:
        """Convert a local partition into a tracked partition."""
        tracking_config = self.config.get("tracking", {})
        if tracking_config.get("enabled", True) is False:
            tracked = Partition(
                frame_index=local_partition.frame_index,
                labels=list(local_partition.labels),
                kind="tracked",
                metadata={
                    **local_partition.metadata,
                    "synchronized_from_previous": False,
                },
            )
            self.state.previous_tracked_partition = tracked
            self._refresh_next_cluster_id(tracked)
            return tracked

        tracked_labels, tracking_metadata = self._track_partition(local_partition, tracking_config)
        tracked = Partition(
            frame_index=local_partition.frame_index,
            labels=tracked_labels,
            kind="tracked",
            metadata={
                **local_partition.metadata,
                "synchronized_from_previous": tracking_metadata.synchronized_from_previous,
                "tracking": tracking_metadata,
            },
        )
        self.state.previous_tracked_partition = tracked
        self._refresh_next_cluster_id(tracked)
        return tracked

    def _track_partition(
        self,
        local_partition: Partition,
        tracking_config: dict,
    ) -> tuple[list[int], TrackingFrameMetadata]:
        """Match the current local partition to the previous tracked partition."""
        overlap_metric = str(tracking_config.get("overlap_metric", "jaccard"))
        match_threshold = float(tracking_config.get("match_threshold", 0.5))
        event_threshold = float(tracking_config.get("event_threshold", 0.1))
        previous = self.state.previous_tracked_partition

        current_clusters = build_cluster_index(local_partition.labels)
        ordered_current = ordered_cluster_labels(current_clusters)
        if previous is None:
            local_to_tracked = {local_label: local_label for local_label in ordered_current}
            tracked_labels = [local_to_tracked[label] for label in local_partition.labels]
            matches = [
                ClusterMatchRecord(
                    local_label=local_label,
                    tracked_label=tracked_id,
                    previous_tracked_label=None,
                    score=0.0,
                    margin=0.0,
                    confidence=0.0,
                    uncertainty=1.0,
                    intersection_size=0,
                    jaccard=0.0,
                    precision=0.0,
                    recall=0.0,
                    is_birth=True,
                )
                for local_label, tracked_id in local_to_tracked.items()
            ]
            metadata = TrackingFrameMetadata(
                overlap_metric=overlap_metric,
                match_threshold=match_threshold,
                event_threshold=event_threshold,
                synchronized_from_previous=False,
                local_to_tracked=local_to_tracked,
                matches=matches,
                births=sorted(local_to_tracked.values()),
            )
            return tracked_labels, metadata

        previous_clusters = build_cluster_index(previous.labels)
        ordered_previous = sorted(previous_clusters)
        pair_stats = build_overlap_matrix(
            current_clusters=current_clusters,
            previous_clusters=previous_clusters,
            overlap_metric=overlap_metric,
        )
        assignments = assign_cluster_matches(
            ordered_current=ordered_current,
            ordered_previous=ordered_previous,
            pair_stats=pair_stats,
            overlap_metric=overlap_metric,
        )

        local_to_tracked: dict[int, int] = {}
        matches: list[ClusterMatchRecord] = []
        births: list[int] = []
        matched_previous: set[int] = set()

        for local_label in ordered_current:
            best_previous, best_stats, margin = best_previous_match(
                local_label=local_label,
                ordered_previous=ordered_previous,
                pair_stats=pair_stats,
                overlap_metric=overlap_metric,
            )
            assigned_previous = assignments.get(local_label)
            assigned_stats = pair_stats.get((local_label, assigned_previous)) if assigned_previous is not None else None
            if (
                assigned_previous is not None
                and assigned_stats is not None
                and assigned_stats.intersection_size > 0
                and assigned_stats.score(overlap_metric) >= match_threshold
            ):
                tracked_label = assigned_previous
                matched_previous.add(assigned_previous)
                previous_tracked_label = assigned_previous
                is_birth = False
                selected_stats = assigned_stats
                score = assigned_stats.score(overlap_metric)
            else:
                tracked_label = self._allocate_cluster_id()
                births.append(tracked_label)
                previous_tracked_label = None
                is_birth = True
                selected_stats = best_stats
                score = best_stats.score(overlap_metric) if best_stats is not None else 0.0

            local_to_tracked[local_label] = tracked_label
            jaccard = selected_stats.jaccard if selected_stats is not None else 0.0
            matches.append(
                ClusterMatchRecord(
                    local_label=local_label,
                    tracked_label=tracked_label,
                    previous_tracked_label=previous_tracked_label,
                    score=score,
                    margin=margin,
                    confidence=jaccard,
                    uncertainty=1.0 - jaccard,
                    intersection_size=selected_stats.intersection_size if selected_stats is not None else 0,
                    jaccard=jaccard,
                    precision=selected_stats.precision if selected_stats is not None else 0.0,
                    recall=selected_stats.recall if selected_stats is not None else 0.0,
                    is_birth=is_birth,
                )
            )

        tracked_labels = [local_to_tracked[label] for label in local_partition.labels]
        deaths = sorted(previous_id for previous_id in ordered_previous if previous_id not in matched_previous)
        splits = detect_splits(
            ordered_previous=ordered_previous,
            ordered_current=ordered_current,
            pair_stats=pair_stats,
            local_to_tracked=local_to_tracked,
            threshold=event_threshold,
        )
        merges = detect_merges(
            ordered_previous=ordered_previous,
            ordered_current=ordered_current,
            pair_stats=pair_stats,
            local_to_tracked=local_to_tracked,
            threshold=event_threshold,
        )
        metadata = TrackingFrameMetadata(
            overlap_metric=overlap_metric,
            match_threshold=match_threshold,
            event_threshold=event_threshold,
            synchronized_from_previous=True,
            local_to_tracked=local_to_tracked,
            matches=matches,
            births=sorted(births),
            deaths=deaths,
            splits=splits,
            merges=merges,
        )
        return tracked_labels, metadata

    def _allocate_cluster_id(self) -> int:
        """Return the next unused tracked cluster id."""
        cluster_id = self.state.next_cluster_id
        self.state.next_cluster_id += 1
        return cluster_id

    def _refresh_next_cluster_id(self, partition: Partition) -> None:
        """Keep the cluster id allocator ahead of any tracked labels in use."""
        if not partition.labels:
            return
        self.state.next_cluster_id = max(self.state.next_cluster_id, max(partition.labels) + 1)


@dataclass(frozen=True)
class OverlapStats:
    """Overlap diagnostics for one previous/current cluster pair."""

    intersection_size: int
    jaccard: float
    precision: float
    recall: float
    f1: float

    def score(self, metric: str) -> float:
        """Return the chosen overlap score."""
        if metric == "jaccard":
            return self.jaccard
        if metric == "f1":
            return self.f1
        if metric == "precision":
            return self.precision
        if metric == "recall":
            return self.recall
        if metric == "intersection":
            return float(self.intersection_size)
        raise ValueError(
            "Unsupported tracking.overlap_metric "
            f"{metric!r}. Supported metrics are jaccard, f1, precision, recall, and intersection."
        )


def build_cluster_index(labels: list[int]) -> dict[int, set[int]]:
    """Group atom indices by cluster label."""
    clusters: dict[int, set[int]] = defaultdict(set)
    for index, label in enumerate(labels):
        clusters[int(label)].add(index)
    return dict(clusters)


def ordered_cluster_labels(cluster_index: dict[int, set[int]]) -> list[int]:
    """Return cluster labels ordered by first atom index, then by label."""
    return sorted(cluster_index, key=lambda label: (min(cluster_index[label]), label))


def build_overlap_matrix(
    *,
    current_clusters: dict[int, set[int]],
    previous_clusters: dict[int, set[int]],
    overlap_metric: str,
) -> dict[tuple[int, int], OverlapStats]:
    """Compute overlap diagnostics for every current/previous cluster pair."""
    pair_stats: dict[tuple[int, int], OverlapStats] = {}
    for current_label, current_atoms in current_clusters.items():
        for previous_label, previous_atoms in previous_clusters.items():
            intersection = len(current_atoms & previous_atoms)
            if intersection == 0:
                pair_stats[(current_label, previous_label)] = OverlapStats(
                    intersection_size=0,
                    jaccard=0.0,
                    precision=0.0,
                    recall=0.0,
                    f1=0.0,
                )
                continue
            precision = intersection / len(current_atoms)
            recall = intersection / len(previous_atoms)
            jaccard = intersection / len(current_atoms | previous_atoms)
            f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
            pair_stats[(current_label, previous_label)] = OverlapStats(
                intersection_size=intersection,
                jaccard=jaccard,
                precision=precision,
                recall=recall,
                f1=f1,
            )
            _ = overlap_metric
    return pair_stats


def assign_cluster_matches(
    *,
    ordered_current: list[int],
    ordered_previous: list[int],
    pair_stats: dict[tuple[int, int], OverlapStats],
    overlap_metric: str,
) -> dict[int, int]:
    """Find a one-to-one assignment between current and previous clusters."""
    if not ordered_current or not ordered_previous:
        return {}
    score_matrix = [
        [
            pair_stats[(current_label, previous_label)].score(overlap_metric)
            for previous_label in ordered_previous
        ]
        for current_label in ordered_current
    ]
    row_ids, col_ids = linear_sum_assignment(score_matrix, maximize=True)
    return {
        ordered_current[row_index]: ordered_previous[col_index]
        for row_index, col_index in zip(row_ids.tolist(), col_ids.tolist())
    }


def best_previous_match(
    *,
    local_label: int,
    ordered_previous: list[int],
    pair_stats: dict[tuple[int, int], OverlapStats],
    overlap_metric: str,
) -> tuple[int | None, OverlapStats | None, float]:
    """Return the best previous cluster for a current cluster plus score margin."""
    if not ordered_previous:
        return None, None, 0.0
    scored_previous = sorted(
        (
            (
                previous_label,
                pair_stats[(local_label, previous_label)],
                pair_stats[(local_label, previous_label)].score(overlap_metric),
            )
            for previous_label in ordered_previous
        ),
        key=lambda item: (-item[2], item[0]),
    )
    best_previous, best_stats, best_score = scored_previous[0]
    second_best = scored_previous[1][2] if len(scored_previous) > 1 else 0.0
    return best_previous, best_stats, best_score - second_best


def detect_splits(
    *,
    ordered_previous: list[int],
    ordered_current: list[int],
    pair_stats: dict[tuple[int, int], OverlapStats],
    local_to_tracked: dict[int, int],
    threshold: float,
) -> dict[int, list[int]]:
    """Detect previous tracked clusters that now overlap multiple current clusters."""
    splits: dict[int, list[int]] = {}
    for previous_label in ordered_previous:
        child_ids = sorted(
            {
                local_to_tracked[current_label]
                for current_label in ordered_current
                if pair_stats[(current_label, previous_label)].recall >= threshold
                and pair_stats[(current_label, previous_label)].intersection_size > 0
            }
        )
        if len(child_ids) > 1:
            splits[previous_label] = child_ids
    return splits


def detect_merges(
    *,
    ordered_previous: list[int],
    ordered_current: list[int],
    pair_stats: dict[tuple[int, int], OverlapStats],
    local_to_tracked: dict[int, int],
    threshold: float,
) -> dict[int, list[int]]:
    """Detect current tracked clusters that overlap multiple previous clusters."""
    merges: dict[int, list[int]] = {}
    for current_label in ordered_current:
        parent_ids = sorted(
            previous_label
            for previous_label in ordered_previous
            if pair_stats[(current_label, previous_label)].precision >= threshold
            and pair_stats[(current_label, previous_label)].intersection_size > 0
        )
        if len(parent_ids) > 1:
            merges[local_to_tracked[current_label]] = parent_ids
    return merges
