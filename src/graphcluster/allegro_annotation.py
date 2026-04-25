# Date: 2026-04-01
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Config-driven orchestration for Allegro edge annotation.

This module intentionally keeps the heavy Allegro / NequIP runtime dependency at
the boundary. The core graphcluster pipeline still consumes ASE-readable
trajectories; this helper just decides whether a raw input trajectory should be
annotated with exported Allegro edge metadata before the normal run continues.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .io.trajectory_reader import TrajectoryReader

ALLEGRO_EDGE_ENERGIES_KEY = "allegro_edge_energies"
ALLEGRO_EDGE_INDICES_KEY = "allegro_edge_indices"


@dataclass
class AllegroPreparationResult:
    """Summarize how Allegro preprocessing affected the effective input."""

    effective_trajectory_path: str
    annotation_artifact: Path | None = None
    annotation_performed: bool = False
    stop_after_annotation: bool = False


def prepare_allegro_input(
    config: dict,
    *,
    progress_callback=None,
) -> AllegroPreparationResult:
    """Prepare the effective trajectory input for an Allegro-backed run."""
    input_config = config.get("input", {})
    trajectory_path = str(input_config.get("trajectory", ""))
    allegro_config = config.get("allegro", {})
    if not allegro_config:
        return AllegroPreparationResult(effective_trajectory_path=trajectory_path)

    mode = str(allegro_config.get("mode", "disabled"))
    if mode == "disabled":
        return AllegroPreparationResult(effective_trajectory_path=trajectory_path)

    progress = progress_callback or (lambda message: None)
    annotated_trajectory_path = str(
        allegro_config.get("annotated_trajectory_path", trajectory_path)
    )

    if mode == "require_precomputed":
        return AllegroPreparationResult(effective_trajectory_path=trajectory_path)

    if mode == "annotate_if_missing":
        if trajectory_has_exported_allegro_edges(config):
            progress(
                "Allegro edge annotation skipped: input trajectory already "
                "contains exported edge metadata."
            )
            return AllegroPreparationResult(effective_trajectory_path=trajectory_path)
        annotation_artifact = run_allegro_annotation(config, progress_callback=progress)
        return AllegroPreparationResult(
            effective_trajectory_path=str(annotation_artifact),
            annotation_artifact=annotation_artifact,
            annotation_performed=True,
        )

    if mode == "annotate_always":
        annotation_artifact = run_allegro_annotation(config, progress_callback=progress)
        return AllegroPreparationResult(
            effective_trajectory_path=str(annotation_artifact),
            annotation_artifact=annotation_artifact,
            annotation_performed=True,
        )

    if mode == "annotate_only":
        annotation_artifact = run_allegro_annotation(config, progress_callback=progress)
        return AllegroPreparationResult(
            effective_trajectory_path=str(annotation_artifact),
            annotation_artifact=annotation_artifact,
            annotation_performed=True,
            stop_after_annotation=True,
        )

    raise ValueError(
        "Unsupported allegro.mode "
        f"{mode!r}. Supported modes are disabled, require_precomputed, "
        "annotate_if_missing, annotate_always, and annotate_only."
    )


def trajectory_has_exported_allegro_edges(config: dict) -> bool:
    """Return whether the configured input already contains Allegro edge fields."""
    reader = TrajectoryReader.from_config(config)
    try:
        frame = next(iter(reader))
    except StopIteration:
        return False

    metadata = frame.metadata or {}
    ase_info = metadata.get("ase_info")
    if isinstance(ase_info, dict):
        return (
            ALLEGRO_EDGE_ENERGIES_KEY in ase_info
            and ALLEGRO_EDGE_INDICES_KEY in ase_info
        )
    return (
        ALLEGRO_EDGE_ENERGIES_KEY in metadata
        and ALLEGRO_EDGE_INDICES_KEY in metadata
    )


def run_allegro_annotation(
    config: dict,
    *,
    progress_callback=None,
) -> Path:
    """Run the external Allegro trajectory annotation helper from config."""
    progress = progress_callback or (lambda message: None)
    allegro_config = config.get("allegro", {})
    input_config = config.get("input", {})
    frames = config.get("frames", {})

    compiled_model = allegro_config.get("compiled_model")
    if not compiled_model:
        raise ValueError(
            "Allegro annotation requires allegro.compiled_model to be set."
        )

    annotated_trajectory_path = allegro_config.get("annotated_trajectory_path")
    if not annotated_trajectory_path:
        raise ValueError(
            "Allegro annotation requires allegro.annotated_trajectory_path to be set."
        )

    try:
        from allegro_ase_edge_export.annotate_trajectory import annotate_trajectory
    except ImportError as exc:
        raise ImportError(
            "Allegro annotation requested, but the optional "
            "`allegro_ase_edge_export` package is not available in this Python "
            "environment."
        ) from exc

    progress(
        "Running Allegro edge annotation: "
        f"input={input_config.get('trajectory')}, "
        f"output={annotated_trajectory_path}"
    )
    output_path = annotate_trajectory(
        compiled_model=str(compiled_model),
        input_path=str(input_config.get("trajectory")),
        output_path=str(annotated_trajectory_path),
        device=str(allegro_config.get("device", "cpu")),
        input_format=input_config.get("format"),
        output_format=allegro_config.get("output_format"),
        start=int(frames.get("start", 0)),
        stop=frames.get("stop"),
        stride=int(frames.get("stride", 1)),
        raw_type_map=normalize_mapping(allegro_config.get("raw_type_map")),
        chemical_species_to_atom_type_map=resolve_species_to_model_type_map(
            allegro_config.get("species_to_model_type_map")
        ),
    )
    return Path(output_path)


def normalize_mapping(mapping: dict | None) -> dict[str, str] | None:
    """Normalize user-provided YAML mappings into a string-to-string dict."""
    if not mapping:
        return None
    return {str(key): str(value) for key, value in mapping.items()}


def resolve_species_to_model_type_map(
    mapping: dict | None,
) -> dict[str, str] | bool:
    """Resolve the species-to-model-type mapping contract for the annotator."""
    normalized = normalize_mapping(mapping)
    if normalized is None:
        return True
    return normalized
