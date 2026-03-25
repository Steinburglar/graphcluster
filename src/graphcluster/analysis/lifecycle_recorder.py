# Date: 2026-03-25
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Streaming lifecycle report recording.

In intuitive terms, this module turns the transient frame bundles flowing
through the runner into a persistent trajectory-level report artifact. It is
meant to support long MD runs without forcing the whole trajectory to remain in
memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..bundle.frame_bundle import FrameBundle


@dataclass
class ClusterLifecycleRecorder:
    """Record lifecycle analysis data incrementally during a streaming run."""

    enabled: bool = False
    output_path: Path | None = None
    write_batch_size: int = 1
    _pending_records: list[dict] = field(default_factory=list, init=False, repr=False)
    _header_written: bool = field(default=False, init=False, repr=False)
    _frames_processed: int = field(default=0, init=False, repr=False)
    _num_atoms: int | None = field(default=None, init=False, repr=False)
    _frame_cluster_counts: list[dict] = field(default_factory=list, init=False, repr=False)
    _atom_switch_counts: list[int] | None = field(default=None, init=False, repr=False)
    _previous_labels: list[int] | None = field(default=None, init=False, repr=False)
    _cluster_first_seen: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _cluster_last_seen: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _cluster_frames_observed: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _total_births: int = field(default=0, init=False, repr=False)
    _total_deaths: int = field(default=0, init=False, repr=False)
    _total_splits: int = field(default=0, init=False, repr=False)
    _total_merges: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_config(cls, config: dict) -> "ClusterLifecycleRecorder":
        """Build a recorder from config."""
        analysis_config = config.get("analysis", {})
        output_path = _resolve_output_path(config, analysis_config)
        return cls(
            enabled=analysis_config.get("enabled", False),
            output_path=output_path,
            write_batch_size=max(1, int(analysis_config.get("write_batch_size", 1))),
        )

    def consume(self, bundle: FrameBundle) -> None:
        """Update the report state from one emitted frame bundle."""
        if not self.enabled:
            return
        if self.output_path is None:
            raise ValueError(
                "Lifecycle report recording requires analysis.output_path or output.directory."
            )
        self._ensure_header()

        tracked_labels = list(bundle.partition.labels)
        if self._num_atoms is None:
            self._num_atoms = len(tracked_labels)
            self._atom_switch_counts = [0 for _ in range(self._num_atoms)]

        changed_atoms = 0
        if self._previous_labels is not None:
            changed_atoms = sum(
                1
                for previous_label, current_label in zip(self._previous_labels, tracked_labels)
                if previous_label != current_label
            )
            for index, (previous_label, current_label) in enumerate(
                zip(self._previous_labels, tracked_labels)
            ):
                if previous_label != current_label:
                    self._atom_switch_counts[index] += 1
        self._previous_labels = tracked_labels

        cluster_sizes = _count_cluster_sizes(tracked_labels)
        for cluster_id in cluster_sizes:
            if cluster_id not in self._cluster_first_seen:
                self._cluster_first_seen[cluster_id] = bundle.frame.index
            self._cluster_last_seen[cluster_id] = bundle.frame.index
            self._cluster_frames_observed[cluster_id] = (
                self._cluster_frames_observed.get(cluster_id, 0) + 1
            )

        tracking_metadata = bundle.partition.metadata.get("tracking")
        births = list(getattr(tracking_metadata, "births", []))
        deaths = list(getattr(tracking_metadata, "deaths", []))
        splits = dict(getattr(tracking_metadata, "splits", {}))
        merges = dict(getattr(tracking_metadata, "merges", {}))
        matches = [
            match.as_dict() for match in getattr(tracking_metadata, "matches", [])
        ]

        self._total_births += len(births)
        self._total_deaths += len(deaths)
        self._total_splits += len(splits)
        self._total_merges += len(merges)

        frame_record = {
            "record_type": "frame",
            "frame_index": bundle.frame.index,
            "num_atoms": len(tracked_labels),
            "num_clusters": len(cluster_sizes),
            "num_changed_atoms": changed_atoms,
            "cluster_sizes": [
                {"cluster_id": cluster_id, "size": size}
                for cluster_id, size in sorted(cluster_sizes.items())
            ],
            "tracking": {
                "births": births,
                "deaths": deaths,
                "splits": [
                    {
                        "previous_cluster_id": cluster_id,
                        "current_cluster_ids": child_ids,
                    }
                    for cluster_id, child_ids in sorted(splits.items())
                ],
                "merges": [
                    {
                        "current_cluster_id": cluster_id,
                        "previous_cluster_ids": parent_ids,
                    }
                    for cluster_id, parent_ids in sorted(merges.items())
                ],
                "matches": matches,
            },
        }
        self._frame_cluster_counts.append(
            {
                "frame_index": bundle.frame.index,
                "num_clusters": len(cluster_sizes),
                "num_changed_atoms": changed_atoms,
            }
        )
        self._frames_processed += 1
        self._pending_records.append(frame_record)
        if len(self._pending_records) >= self.write_batch_size:
            self._flush_pending_records()

    def finalize(self) -> Path | None:
        """Flush pending frame records and append a final summary record."""
        if not self.enabled:
            return None
        if self.output_path is None:
            raise ValueError(
                "Lifecycle report recording requires analysis.output_path or output.directory."
            )
        self._ensure_header()
        self._flush_pending_records()
        summary_record = {
            "record_type": "summary",
            "summary": {
                "num_frames": self._frames_processed,
                "num_atoms": self._num_atoms or 0,
                "num_tracked_clusters": len(self._cluster_first_seen),
                "total_births": self._total_births,
                "total_deaths": self._total_deaths,
                "total_splits": self._total_splits,
                "total_merges": self._total_merges,
            },
            "frame_cluster_counts": list(self._frame_cluster_counts),
            "atom_switch_counts": list(self._atom_switch_counts or []),
            "cluster_lifetimes": [
                {
                    "cluster_id": cluster_id,
                    "first_seen_frame": self._cluster_first_seen[cluster_id],
                    "last_seen_frame": self._cluster_last_seen[cluster_id],
                    "frames_observed": self._cluster_frames_observed[cluster_id],
                }
                for cluster_id in sorted(self._cluster_first_seen)
            ],
        }
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary_record, sort_keys=True))
            handle.write("\n")
        return self.output_path

    def artifact_path(self) -> Path | None:
        """Return the configured report artifact path."""
        return self.output_path if self.enabled else None

    def _ensure_header(self) -> None:
        """Create the output file and write the header once."""
        if self._header_written:
            return
        if self.output_path is None:
            raise ValueError("Cannot write report header without an output path.")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.output_path.exists():
            self.output_path.unlink()
        header = {
            "record_type": "header",
            "format": "graphcluster.cluster_lifecycle_report",
            "version": 1,
        }
        with self.output_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(header, sort_keys=True))
            handle.write("\n")
        self._header_written = True

    def _flush_pending_records(self) -> None:
        """Append buffered frame records to disk."""
        if not self._pending_records or self.output_path is None:
            return
        with self.output_path.open("a", encoding="utf-8") as handle:
            for record in self._pending_records:
                handle.write(json.dumps(record, sort_keys=True))
                handle.write("\n")
        self._pending_records.clear()


def _resolve_output_path(config: dict, analysis_config: dict) -> Path | None:
    """Resolve the lifecycle report artifact path."""
    explicit_path = analysis_config.get("output_path")
    if explicit_path:
        return Path(explicit_path)

    output_config = config.get("output", {})
    output_directory = output_config.get("directory")
    if output_directory:
        return Path(output_directory) / "cluster_lifecycle_report.jsonl"

    if analysis_config.get("enabled", False):
        return Path("outputs") / "cluster_lifecycle_report.jsonl"
    return None


def _count_cluster_sizes(labels: list[int]) -> dict[int, int]:
    """Count atoms per tracked cluster."""
    sizes: dict[int, int] = {}
    for label in labels:
        sizes[label] = sizes.get(label, 0) + 1
    return sizes
