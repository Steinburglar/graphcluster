# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Trajectory-level lifecycle report artifact access.

In intuitive terms, this is the lightweight user-facing object loaded from the
streaming lifecycle report artifact written during a run. It should stay easier
to hold in memory than the original MD trajectory while still giving notebooks
and downstream tooling access to useful event and summary data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ClusterLifecycleReport:
    """Store trajectory-level lifecycle information loaded from an artifact."""

    summary: dict[str, Any] = field(default_factory=dict)
    frame_records: list[dict[str, Any]] = field(default_factory=list)
    atom_switch_counts: list[int] = field(default_factory=list)
    cluster_lifetimes: list[dict[str, Any]] = field(default_factory=list)
    source_path: Path | None = None

    @classmethod
    def from_path(cls, path: str | Path) -> "ClusterLifecycleReport":
        """Load a report from a JSON Lines lifecycle artifact."""
        artifact_path = Path(path)
        frame_records: list[dict[str, Any]] = []
        summary: dict[str, Any] = {}
        atom_switch_counts: list[int] = []
        cluster_lifetimes: list[dict[str, Any]] = []
        with artifact_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                record_type = record.get("record_type")
                if record_type == "frame":
                    frame_records.append(record)
                elif record_type == "summary":
                    summary = dict(record.get("summary", {}))
                    atom_switch_counts = list(record.get("atom_switch_counts", []))
                    cluster_lifetimes = list(record.get("cluster_lifetimes", []))
        return cls(
            summary=summary,
            frame_records=frame_records,
            atom_switch_counts=atom_switch_counts,
            cluster_lifetimes=cluster_lifetimes,
            source_path=artifact_path,
        )

    def get_births(self) -> list[dict[str, Any]]:
        """Return birth events grouped by frame."""
        return [
            {
                "frame_index": record["frame_index"],
                "cluster_ids": list(record["tracking"]["births"]),
            }
            for record in self.frame_records
            if record["tracking"]["births"]
        ]

    def get_deaths(self) -> list[dict[str, Any]]:
        """Return death events grouped by frame."""
        return [
            {
                "frame_index": record["frame_index"],
                "cluster_ids": list(record["tracking"]["deaths"]),
            }
            for record in self.frame_records
            if record["tracking"]["deaths"]
        ]

    def get_splits(self) -> list[dict[str, Any]]:
        """Return split events grouped by frame."""
        return [
            {
                "frame_index": record["frame_index"],
                "events": list(record["tracking"]["splits"]),
            }
            for record in self.frame_records
            if record["tracking"]["splits"]
        ]

    def get_merges(self) -> list[dict[str, Any]]:
        """Return merge events grouped by frame."""
        return [
            {
                "frame_index": record["frame_index"],
                "events": list(record["tracking"]["merges"]),
            }
            for record in self.frame_records
            if record["tracking"]["merges"]
        ]

    def get_frame_cluster_counts(self) -> list[dict[str, Any]]:
        """Return per-frame tracked-cluster counts."""
        return [
            {
                "frame_index": record["frame_index"],
                "num_clusters": record["num_clusters"],
                "num_changed_atoms": record["num_changed_atoms"],
            }
            for record in self.frame_records
        ]

    def get_atom_switch_counts(self) -> list[int]:
        """Return the number of tracked-cluster changes per atom."""
        return list(self.atom_switch_counts)

    def get_cluster_lifetimes(self) -> list[dict[str, Any]]:
        """Return simple tracked-cluster lifetime records."""
        return list(self.cluster_lifetimes)
