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

    def get_summary_table(self) -> dict[str, Any]:
        """Return the headline run summary as a plain dictionary."""
        return dict(self.summary)

    def get_event_counts(self) -> dict[str, int]:
        """Return total birth/death/split/merge counts from the summary."""
        return {
            "total_births": int(self.summary.get("total_births", 0)),
            "total_deaths": int(self.summary.get("total_deaths", 0)),
            "total_splits": int(self.summary.get("total_splits", 0)),
            "total_merges": int(self.summary.get("total_merges", 0)),
        }

    def get_top_atoms_by_switches(
        self,
        n: int = 10,
        *,
        min_switches: int = 1,
    ) -> list[dict[str, int]]:
        """Return the atoms that changed tracked cluster most frequently."""
        records = [
            {"atom_index": atom_index, "switch_count": int(switch_count)}
            for atom_index, switch_count in enumerate(self.atom_switch_counts)
            if int(switch_count) >= min_switches
        ]
        records.sort(key=lambda record: (-record["switch_count"], record["atom_index"]))
        return records[: max(int(n), 0)]

    def get_num_active_atoms(self, *, min_switches: int = 1) -> int:
        """Return the number of atoms whose tracked label changed enough times."""
        return sum(int(count) >= min_switches for count in self.atom_switch_counts)

    def get_cluster_lifetimes_sorted(
        self,
        *,
        descending: bool = True,
    ) -> list[dict[str, Any]]:
        """Return lifetime records sorted by frames observed."""
        return sorted(
            self.cluster_lifetimes,
            key=lambda record: (int(record.get("frames_observed", 0)), -int(record.get("cluster_id", 0))),
            reverse=descending,
        )

    def get_longest_lived_clusters(self, n: int = 10) -> list[dict[str, Any]]:
        """Return the longest-lived tracked clusters."""
        return self.get_cluster_lifetimes_sorted(descending=True)[: max(int(n), 0)]

    def plot_cluster_count_timeseries(self, *, figsize: tuple[float, float] = (8, 6)):
        """Plot tracked-cluster count and atom-change activity versus frame."""
        plt = _import_matplotlib_pyplot()
        frame_counts = self.get_frame_cluster_counts()
        frame_indices = [record["frame_index"] for record in frame_counts]
        num_clusters = [record["num_clusters"] for record in frame_counts]
        num_changed_atoms = [record["num_changed_atoms"] for record in frame_counts]

        fig, axes = plt.subplots(2, 1, figsize=figsize, sharex=True)
        axes[0].plot(frame_indices, num_clusters, marker="o")
        axes[0].set_ylabel("Tracked clusters")
        axes[0].set_title("Clusters per frame")

        axes[1].plot(frame_indices, num_changed_atoms, marker="o", color="tab:orange")
        axes[1].set_xlabel("Frame index")
        axes[1].set_ylabel("Atoms changing cluster")
        axes[1].set_title("Per-frame cluster-change activity")

        fig.tight_layout()
        return fig, axes

    def plot_atom_switch_histogram(self, *, figsize: tuple[float, float] = (7, 4)):
        """Plot the distribution of tracked-cluster changes per atom."""
        plt = _import_matplotlib_pyplot()
        atom_switch_counts = self.get_atom_switch_counts()
        fig, ax = plt.subplots(figsize=figsize)
        ax.hist(
            atom_switch_counts,
            bins=_integer_histogram_bins(atom_switch_counts, minimum_left_edge=0),
            align="left",
            rwidth=0.9,
        )
        ax.set_xlabel("Tracked-cluster changes per atom")
        ax.set_ylabel("Number of atoms")
        ax.set_title("Atom activity histogram")
        return fig, ax

    def plot_cluster_lifetime_histogram(self, *, figsize: tuple[float, float] = (7, 4)):
        """Plot the distribution of tracked-cluster lifetimes."""
        plt = _import_matplotlib_pyplot()
        lifetime_lengths = [
            int(record.get("frames_observed", 0))
            for record in self.get_cluster_lifetimes_sorted(descending=True)
        ]
        fig, ax = plt.subplots(figsize=figsize)
        ax.hist(
            lifetime_lengths,
            bins=_integer_histogram_bins(lifetime_lengths, minimum_left_edge=1),
            align="left",
            rwidth=0.9,
        )
        ax.set_xlabel("Frames observed")
        ax.set_ylabel("Number of tracked clusters")
        ax.set_title("Tracked-cluster lifetime histogram")
        return fig, ax


def _import_matplotlib_pyplot():
    """Import matplotlib lazily so reports remain cheap to load."""
    import matplotlib.pyplot as plt

    return plt


def _integer_histogram_bins(values: list[int], *, minimum_left_edge: int) -> list[int]:
    """Build inclusive histogram bins for small integer-valued summaries."""
    if not values:
        return [minimum_left_edge, minimum_left_edge + 1]
    upper = max(max(int(value) for value in values) + 2, minimum_left_edge + 2)
    return list(range(minimum_left_edge, upper))
