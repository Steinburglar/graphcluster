# Date: 2026-03-25
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Structured metadata emitted by the online cluster tracker.

These dataclasses capture the frame-local bookkeeping produced while matching
the current local partition against the previous tracked partition. The tracker
stores one :class:`TrackingFrameMetadata` object on each tracked partition so
later trajectory analysis can consume the matching decisions without having to
recompute them from scratch.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ClusterMatchRecord:
    """Describe how one current local cluster was handled by the tracker."""

    local_label: int
    tracked_label: int
    previous_tracked_label: int | None
    score: float
    margin: float
    confidence: float
    uncertainty: float
    intersection_size: int
    jaccard: float
    precision: float
    recall: float
    is_birth: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-`dict` representation."""
        return asdict(self)


@dataclass(slots=True)
class TrackingFrameMetadata:
    """Store frame-level cluster matching events and diagnostics."""

    overlap_metric: str
    match_threshold: float
    event_threshold: float
    synchronized_from_previous: bool
    local_to_tracked: dict[int, int] = field(default_factory=dict)
    matches: list[ClusterMatchRecord] = field(default_factory=list)
    births: list[int] = field(default_factory=list)
    deaths: list[int] = field(default_factory=list)
    splits: dict[int, list[int]] = field(default_factory=dict)
    merges: dict[int, list[int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a plain-`dict` representation."""
        data = asdict(self)
        data["matches"] = [match.as_dict() for match in self.matches]
        return data
