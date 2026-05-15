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

    def has_cluster_energy(self) -> bool:
        """Return whether any frame record contains cluster energy summaries."""
        return any("cluster_energy" in record for record in self.frame_records)

    def get_frame_cluster_energies(self) -> list[dict[str, Any]]:
        """Return frame-local cluster energy summaries when present."""
        return [
            {
                "frame_index": record["frame_index"],
                "cluster_energy": _normalize_frame_cluster_energy_record(record["cluster_energy"]),
            }
            for record in self.frame_records
            if "cluster_energy" in record
        ]

    def get_cluster_energy_timeseries(self, cluster_id: int) -> list[dict[str, Any]]:
        """Return raw pre-energy and reconstructed model-energy data for one cluster."""
        series: list[dict[str, Any]] = []
        for record in self.frame_records:
            cluster_energy = record.get("cluster_energy")
            if not isinstance(cluster_energy, dict):
                continue
            normalized_frame_record = _normalize_frame_cluster_energy_record(cluster_energy)
            for cluster_record in normalized_frame_record.get("clusters", []):
                normalized_record = _normalize_cluster_energy_record(cluster_record)
                if int(normalized_record.get("cluster_id", -1)) != int(cluster_id):
                    continue
                series.append(
                    {
                        "frame_index": record["frame_index"],
                        "cluster_id": int(normalized_record["cluster_id"]),
                        "size": int(normalized_record.get("size", 0)),
                        "internal_energy": float(normalized_record.get("internal_energy", 0.0)),
                        "external_energy": float(normalized_record.get("external_energy", 0.0)),
                        "combined_energy": float(normalized_record.get("combined_energy", 0.0)),
                        "internal_energy_per_atom": float(
                            normalized_record.get("internal_energy_per_atom", 0.0)
                        ),
                        "external_energy_per_atom": float(
                            normalized_record.get("external_energy_per_atom", 0.0)
                        ),
                        "combined_energy_per_atom": float(
                            normalized_record.get("combined_energy_per_atom", 0.0)
                        ),
                        "internal_model_energy": float(
                            normalized_record.get("internal_model_energy", 0.0)
                        ),
                        "external_model_energy": float(
                            normalized_record.get("external_model_energy", 0.0)
                        ),
                        "shift_energy": float(normalized_record.get("shift_energy", 0.0)),
                        "combined_model_energy": float(
                            normalized_record.get("combined_model_energy", 0.0)
                        ),
                        "internal_model_energy_per_atom": float(
                            normalized_record.get("internal_model_energy_per_atom", 0.0)
                        ),
                        "external_model_energy_per_atom": float(
                            normalized_record.get("external_model_energy_per_atom", 0.0)
                        ),
                        "shift_energy_per_atom": float(
                            normalized_record.get("shift_energy_per_atom", 0.0)
                        ),
                        "combined_model_energy_per_atom": float(
                            normalized_record.get("combined_model_energy_per_atom", 0.0)
                        ),
                    }
                )
        return series

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

    def plot_cluster_energy_timeseries(
        self,
        cluster_id: int,
        *,
        components: tuple[str, ...] = ("internal_energy", "external_energy", "combined_energy"),
        figsize: tuple[float, float] = (8, 8),
    ):
        """Plot raw pre-energy or reconstructed model-energy fields versus frame."""
        plt = _import_matplotlib_pyplot()
        series = self.get_cluster_energy_timeseries(cluster_id)
        if not series:
            raise ValueError(
                f"No cluster energy records were found for tracked cluster {cluster_id}."
            )

        valid_components = {
            "internal_energy",
            "external_energy",
            "combined_energy",
            "internal_energy_per_atom",
            "external_energy_per_atom",
            "combined_energy_per_atom",
            "internal_model_energy",
            "external_model_energy",
            "shift_energy",
            "combined_model_energy",
            "internal_model_energy_per_atom",
            "external_model_energy_per_atom",
            "shift_energy_per_atom",
            "combined_model_energy_per_atom",
        }
        unknown_components = [component for component in components if component not in valid_components]
        if unknown_components:
            raise ValueError(
                "Unsupported cluster energy component(s) "
                f"{unknown_components!r}. Supported values are {sorted(valid_components)}."
            )

        frame_indices = [record["frame_index"] for record in series]
        fig, axes = plt.subplots(len(components), 1, figsize=figsize, sharex=True)
        if len(components) == 1:
            axes = [axes]
        for axis, component in zip(axes, components, strict=True):
            axis.plot(frame_indices, [record[component] for record in series], marker="o")
            axis.set_ylabel(component)
            axis.set_title(f"Tracked cluster {cluster_id} {component}")
        axes[-1].set_xlabel("Frame index")
        fig.tight_layout()
        return fig, axes


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


def _normalize_cluster_energy_record(cluster_record: dict[str, Any]) -> dict[str, Any]:
    """Return cluster energy record with per-atom fields filled in.

    Older artifacts may only contain total energies plus size. Compute
    per-atom values lazily here so notebooks can read both old and new reports.
    """
    normalized = dict(cluster_record)
    size = int(normalized.get("size", 0))
    if size <= 0:
        normalized.setdefault("internal_energy_per_atom", 0.0)
        normalized.setdefault("external_energy_per_atom", 0.0)
        normalized.setdefault("combined_energy_per_atom", 0.0)
        return normalized

    size_float = float(size)
    internal_energy = float(normalized.get("internal_energy", 0.0))
    external_energy = float(normalized.get("external_energy", 0.0))
    combined_energy = float(normalized.get("combined_energy", internal_energy + external_energy))
    normalized.setdefault("combined_energy", combined_energy)
    normalized.setdefault("internal_energy_per_atom", internal_energy / size_float)
    normalized.setdefault("external_energy_per_atom", external_energy / size_float)
    normalized.setdefault("combined_energy_per_atom", combined_energy / size_float)
    return normalized


def _normalize_frame_cluster_energy_record(cluster_energy: dict[str, Any]) -> dict[str, Any]:
    """Normalize frame-local cluster energy record, merging reconstruction if present."""
    normalized = dict(cluster_energy)
    raw_clusters = [
        _normalize_cluster_energy_record(cluster_record)
        for cluster_record in cluster_energy.get("clusters", [])
    ]

    reconstruction = cluster_energy.get("model_energy_reconstruction")
    reconstructed_by_cluster: dict[int, dict[str, Any]] = {}
    if isinstance(reconstruction, dict):
        for cluster_record in reconstruction.get("clusters", []):
            normalized_record = _normalize_cluster_model_energy_record(cluster_record)
            reconstructed_by_cluster[int(normalized_record["cluster_id"])] = normalized_record

    merged_clusters: list[dict[str, Any]] = []
    for raw_cluster_record in raw_clusters:
        cluster_id = int(raw_cluster_record["cluster_id"])
        merged_clusters.append(
            {
                **raw_cluster_record,
                **reconstructed_by_cluster.get(cluster_id, {}),
            }
        )
    normalized["clusters"] = merged_clusters
    return normalized


def _normalize_cluster_model_energy_record(cluster_record: dict[str, Any]) -> dict[str, Any]:
    """Return reconstructed model-energy record with per-atom fields filled in."""
    normalized = dict(cluster_record)
    size = int(normalized.get("size", 0))
    if size <= 0:
        for field_name in (
            "internal_model_energy_per_atom",
            "external_model_energy_per_atom",
            "shift_energy_per_atom",
            "combined_model_energy_per_atom",
        ):
            normalized.setdefault(field_name, 0.0)
        return normalized

    size_float = float(size)
    internal_model_energy = float(normalized.get("internal_model_energy", 0.0))
    external_model_energy = float(normalized.get("external_model_energy", 0.0))
    shift_energy = float(normalized.get("shift_energy", 0.0))
    combined_model_energy = float(
        normalized.get(
            "combined_model_energy",
            internal_model_energy + external_model_energy + shift_energy,
        )
    )
    normalized.setdefault("combined_model_energy", combined_model_energy)
    normalized.setdefault("internal_model_energy_per_atom", internal_model_energy / size_float)
    normalized.setdefault("external_model_energy_per_atom", external_model_energy / size_float)
    normalized.setdefault("shift_energy_per_atom", shift_energy / size_float)
    normalized.setdefault("combined_model_energy_per_atom", combined_model_energy / size_float)
    return normalized
