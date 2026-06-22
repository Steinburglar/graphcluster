# Date: 2026-03-25
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Streaming lifecycle report recording.

In intuitive terms, this module turns the transient frame bundles flowing
through the runner into a persistent trajectory-level report artifact. It is
meant to support long MD runs without forcing the whole trajectory to remain in
memory.
"""

from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..bundle.frame_bundle import FrameBundle
from .cluster_energy import (
    compute_cluster_raw_allegro_energies,
    compute_cluster_reconstructed_model_energies,
    frame_has_raw_allegro_edges,
)


@dataclass
class ClusterLifecycleRecorder:
    """Record lifecycle analysis data incrementally during a streaming run."""

    enabled: bool = False
    output_path: Path | None = None
    write_batch_size: int = 1
    cluster_energy_enabled: bool = False
    cluster_energy_source: str = "allegro_raw"
    cluster_energy_require_available: bool = True
    cluster_energy_model_reconstruction_enabled: bool = False
    cluster_energy_species_scales: dict[str, float] = field(default_factory=dict)
    cluster_energy_species_shifts: dict[str, float] = field(default_factory=dict)
    cluster_energy_avg_num_neighbors: float | dict[str, float] | None = None
    reaction_tracking_enabled: bool = False
    reaction_tracking_top_n_frames: int = 10
    reaction_tracking_required_species: tuple[str, ...] = field(default_factory=tuple)
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
    _reaction_previous_cluster_energy: dict[int, float] = field(
        default_factory=dict, init=False, repr=False
    )
    _reaction_top_frames: list[tuple[float, int, dict]] = field(
        default_factory=list, init=False, repr=False
    )
    _reaction_frames_scored: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_config(cls, config: dict) -> "ClusterLifecycleRecorder":
        """Build a recorder from config."""
        artifacts_config = config.get("artifacts", {})
        lifecycle_config = artifacts_config.get("lifecycle_report", {})
        cluster_energy_config = dict(lifecycle_config.get("cluster_energy") or {})
        reconstruction_config = dict(
            cluster_energy_config.get("model_energy_reconstruction") or {}
        )
        reaction_tracking_config = dict(lifecycle_config.get("reaction_tracking") or {})
        output_path = _resolve_output_path(artifacts_config, lifecycle_config)
        return cls(
            enabled=lifecycle_config.get("enabled", False),
            output_path=output_path,
            write_batch_size=max(1, int(lifecycle_config.get("write_batch_size", 1))),
            cluster_energy_enabled=bool(cluster_energy_config.get("enabled", False)),
            cluster_energy_source=str(cluster_energy_config.get("source", "allegro_raw")),
            cluster_energy_require_available=bool(
                cluster_energy_config.get("require_available", True)
            ),
            cluster_energy_model_reconstruction_enabled=bool(
                reconstruction_config.get("enabled", False)
            ),
            cluster_energy_species_scales={
                str(key): float(value)
                for key, value in dict(reconstruction_config.get("species_scales") or {}).items()
            },
            cluster_energy_species_shifts={
                str(key): float(value)
                for key, value in dict(reconstruction_config.get("species_shifts") or {}).items()
            },
            cluster_energy_avg_num_neighbors=_normalize_avg_num_neighbors(
                reconstruction_config.get("avg_num_neighbors")
            ),
            reaction_tracking_enabled=bool(reaction_tracking_config.get("enabled", False)),
            reaction_tracking_top_n_frames=max(
                0, int(reaction_tracking_config.get("top_n_frames", 10))
            ),
            reaction_tracking_required_species=_normalize_required_species(
                reaction_tracking_config.get("required_species")
            ),
        )

    def consume(self, bundle: FrameBundle) -> None:
        """Update the report state from one emitted frame bundle."""
        if not self.enabled:
            return
        if self.output_path is None:
            raise ValueError(
                "Lifecycle report recording requires lifecycle_report.output_path or artifacts.directory."
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
        cluster_energy_record = self._build_cluster_energy_record(bundle)
        reaction_tracking_record = self._build_reaction_tracking_record(
            bundle, cluster_energy_record
        )

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
        if cluster_energy_record is not None:
            frame_record["cluster_energy"] = cluster_energy_record
        if reaction_tracking_record is not None:
            frame_record["reaction_tracking"] = reaction_tracking_record
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
                "Lifecycle report recording requires lifecycle_report.output_path or artifacts.directory."
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
        if self.reaction_tracking_enabled:
            summary_record["summary"]["reaction_tracking"] = {
                "enabled": True,
                "energy_field": "combined_model_energy",
                "signal_kind": "raw_delta",
                "required_species": list(self.reaction_tracking_required_species),
                "top_n_frames": self.reaction_tracking_top_n_frames,
                "frames_scored": self._reaction_frames_scored,
                "top_frames": [
                    reaction_record
                    for _, _, reaction_record in sorted(
                        self._reaction_top_frames, key=lambda item: (-item[0], item[1])
                    )
                ],
            }
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary_record, sort_keys=True))
            handle.write("\n")
        return self.output_path

    def _build_cluster_energy_record(self, bundle: FrameBundle) -> dict | None:
        """Build per-cluster raw energy summaries for one frame when enabled."""
        if not self.cluster_energy_enabled:
            return None
        if self.cluster_energy_source != "allegro_raw":
            raise ValueError(
                "Unsupported lifecycle_report.cluster_energy.source "
                f"{self.cluster_energy_source!r}. Supported values are ['allegro_raw']."
            )
        if not frame_has_raw_allegro_edges(bundle):
            if self.cluster_energy_require_available:
                raise ValueError(
                    "Raw Allegro cluster energy tracking requires "
                    f"{'allegro_edge_indices'!r} and {'allegro_edge_energies'!r} in "
                    "frame metadata or frame.metadata['ase_info']. This analysis can run "
                    "with any clustering edge kind as long as the source frames carry "
                    "Allegro edge annotations."
                )
            return None
        return {
            "source": "allegro_raw",
            "directed": True,
            "clusters": compute_cluster_raw_allegro_energies(bundle),
            "model_energy_reconstruction": (
                {
                    "enabled": True,
                    "source_atom_owns_edge": True,
                    "clusters": compute_cluster_reconstructed_model_energies(
                        bundle,
                        species_scales=self.cluster_energy_species_scales,
                        species_shifts=self.cluster_energy_species_shifts,
                        avg_num_neighbors=self.cluster_energy_avg_num_neighbors,
                    ),
                }
                if self.cluster_energy_model_reconstruction_enabled
                else None
            ),
        }

    def _build_reaction_tracking_record(
        self,
        bundle: FrameBundle,
        cluster_energy_record: dict | None,
    ) -> dict | None:
        """Build a per-frame reaction score from raw cluster model-energy deltas."""
        if not self.reaction_tracking_enabled:
            return None
        if cluster_energy_record is None:
            raise ValueError(
                "Reaction tracking requires lifecycle_report.cluster_energy.enabled = true."
            )

        reconstruction = cluster_energy_record.get("model_energy_reconstruction")
        if not isinstance(reconstruction, dict) or not reconstruction.get("enabled", False):
            raise ValueError(
                "Reaction tracking requires lifecycle_report.cluster_energy."
                "model_energy_reconstruction.enabled = true because it uses reconstructed "
                "cluster model energies as E_atom."
            )

        species_labels = _resolve_frame_species_labels(bundle)
        tracked_labels = list(bundle.partition.labels)
        cluster_species_counts = _count_cluster_species(tracked_labels, species_labels)

        eligible_cluster_count = 0
        best_candidate: dict[str, object] | None = None
        for cluster_record in reconstruction.get("clusters", []):
            cluster_id = int(cluster_record["cluster_id"])
            if not _cluster_has_required_species(
                cluster_species_counts.get(cluster_id, {}),
                self.reaction_tracking_required_species,
            ):
                continue
            eligible_cluster_count += 1

            current_energy = float(cluster_record.get("combined_model_energy", 0.0))
            previous_energy = self._reaction_previous_cluster_energy.get(cluster_id)
            self._reaction_previous_cluster_energy[cluster_id] = current_energy
            if previous_energy is None:
                continue

            delta_energy = current_energy - previous_energy
            score = abs(delta_energy)
            candidate = {
                "cluster_id": cluster_id,
                "size": int(cluster_record.get("size", 0)),
                "species_counts": dict(cluster_species_counts.get(cluster_id, {})),
                "previous_energy": previous_energy,
                "current_energy": current_energy,
                "delta_energy": delta_energy,
                "score": score,
            }
            if best_candidate is None or score > float(best_candidate["score"]):
                best_candidate = candidate

        if best_candidate is not None and float(best_candidate["score"]) > 0.0:
            self._reaction_frames_scored += 1
            self._update_reaction_top_frames(bundle.frame.index, best_candidate)

        return {
            "enabled": True,
            "energy_field": "combined_model_energy",
            "signal_kind": "raw_delta",
            "required_species": list(self.reaction_tracking_required_species),
            "eligible_cluster_count": eligible_cluster_count,
            "score": float(best_candidate["score"]) if best_candidate is not None else 0.0,
            "best_cluster_id": (
                int(best_candidate["cluster_id"]) if best_candidate is not None else None
            ),
            "best_cluster_size": (
                int(best_candidate["size"]) if best_candidate is not None else None
            ),
            "best_cluster_species_counts": (
                dict(best_candidate["species_counts"]) if best_candidate is not None else {}
            ),
            "best_previous_energy": (
                float(best_candidate["previous_energy"]) if best_candidate is not None else None
            ),
            "best_current_energy": (
                float(best_candidate["current_energy"]) if best_candidate is not None else None
            ),
            "best_delta_energy": (
                float(best_candidate["delta_energy"]) if best_candidate is not None else None
            ),
        }

    def _update_reaction_top_frames(self, frame_index: int, candidate: dict[str, object]) -> None:
        """Maintain a bounded top-N list of the most reactive frames."""
        top_n = int(self.reaction_tracking_top_n_frames)
        if top_n <= 0:
            return

        reaction_record = {
            "frame_index": frame_index,
            "score": float(candidate["score"]),
            "best_cluster_id": int(candidate["cluster_id"]),
            "best_cluster_size": int(candidate["size"]),
            "best_cluster_species_counts": dict(candidate["species_counts"]),
            "best_previous_energy": float(candidate["previous_energy"]),
            "best_current_energy": float(candidate["current_energy"]),
            "best_delta_energy": float(candidate["delta_energy"]),
        }
        heap_item = (reaction_record["score"], frame_index, reaction_record)
        if len(self._reaction_top_frames) < top_n:
            heapq.heappush(self._reaction_top_frames, heap_item)
            return
        if heap_item[0] > self._reaction_top_frames[0][0]:
            heapq.heapreplace(self._reaction_top_frames, heap_item)

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


def _resolve_output_path(artifacts_config: dict, lifecycle_config: dict) -> Path | None:
    """Resolve the lifecycle report artifact path."""
    explicit_path = lifecycle_config.get("output_path")
    if explicit_path:
        return Path(explicit_path)

    output_directory = artifacts_config.get("directory")
    if output_directory:
        return Path(output_directory) / "cluster_lifecycle_report.jsonl"

    if lifecycle_config.get("enabled", False):
        return Path("outputs") / "cluster_lifecycle_report.jsonl"
    return None


def _count_cluster_sizes(labels: list[int]) -> dict[int, int]:
    """Count atoms per tracked cluster."""
    sizes: dict[int, int] = {}
    for label in labels:
        sizes[label] = sizes.get(label, 0) + 1
    return sizes


def _count_cluster_species(
    labels: list[int],
    species_labels: list[str],
) -> dict[int, dict[str, int]]:
    """Count species per tracked cluster."""
    cluster_species: dict[int, dict[str, int]] = {}
    for cluster_id, species_label in zip(labels, species_labels, strict=True):
        species_counts = cluster_species.setdefault(cluster_id, {})
        species_counts[species_label] = species_counts.get(species_label, 0) + 1
    return cluster_species


def _cluster_has_required_species(
    cluster_species_counts: dict[str, int],
    required_species: tuple[str, ...],
) -> bool:
    """Return whether a cluster contains every required species."""
    return all(int(cluster_species_counts.get(species_label, 0)) > 0 for species_label in required_species)


def _resolve_frame_species_labels(bundle: FrameBundle) -> list[str]:
    """Resolve one species label per atom for a frame bundle."""
    frame = bundle.frame
    if frame.chemical_symbols is not None:
        return [str(label) for label in frame.chemical_symbols]
    if frame.atom_types is not None:
        return [str(label) for label in frame.atom_types]
    raise ValueError(
        "Reaction tracking requires frame.chemical_symbols or frame.atom_types "
        f"to be available in frame {frame.index}."
    )


def _normalize_required_species(value) -> tuple[str, ...]:
    """Normalize optional required_species config into a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    raise TypeError(
        "lifecycle_report.reaction_tracking.required_species must be a string or list."
    )


def _normalize_avg_num_neighbors(value):
    """Normalize optional avg_num_neighbors config into float/dict/None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return {str(key): float(item) for key, item in value.items()}
    raise TypeError(
        "cluster_energy.model_energy_reconstruction.avg_num_neighbors must be a float "
        "or species-keyed dict."
    )
