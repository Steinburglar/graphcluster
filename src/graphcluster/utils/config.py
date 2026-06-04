# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Configuration loading helpers.

In intuitive terms, this module is the narrow place where YAML config files are
turned into Python dictionaries before the rest of the pipeline consumes them.

Who touches this:
- CLI and runner code
- people evolving config schema

Who this touches:
- the filesystem
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(config_path: str | Path) -> dict:
    """Load and normalize a YAML config file into the canonical schema."""
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return normalize_config(raw, config_path=path)


def normalize_config(data: dict, *, config_path: str | Path | None = None) -> dict:
    """Normalize user config into the repository's canonical runtime schema."""
    if not isinstance(data, dict):
        raise ValueError("The top-level config must be a YAML mapping.")

    source = dict(data.get("source") or {})
    source_path = source.get("path")
    if not source_path:
        raise ValueError("Config requires source.path to be set.")

    selection = dict(data.get("selection") or {})
    edges = dict(data.get("edges") or {})
    artifacts = dict(data.get("artifacts") or {})
    visualization = dict(artifacts.get("visualization") or {})
    lifecycle_report = dict(artifacts.get("lifecycle_report") or {})

    normalized = {
        "config_path": str(config_path) if config_path is not None else None,
        "source": {
            "backend": source.get("backend", "ase"),
            "path": str(source_path),
            "format": source.get("format"),
            "type_map": dict(source.get("type_map") or {}),
            "cutoff_radius": source.get("cutoff_radius"),
        },
        "selection": {
            "start": int(selection.get("start", 0)),
            "stop": selection.get("stop"),
            "stride": int(selection.get("stride", 1)),
        },
        "edges": {
            "kind": str(edges.get("kind", "binary")),
            "directed": bool(edges.get("directed", False)),
            "cutoff": edges.get("cutoff"),
            "sigma": edges.get("sigma"),
            "epsilon": edges.get("epsilon"),
            "energy_to_weight": str(edges.get("energy_to_weight", "abs_negative_sum")),
            "energy_field": str(edges.get("energy_field", "raw")),
            "species_shifts": dict(edges.get("species_shifts") or {}),
            "avg_num_neighbors": edges.get("avg_num_neighbors"),
        },
        "partition": dict(data.get("partition") or {}),
        "tracking": dict(data.get("tracking") or {}),
        "artifacts": {
            "directory": artifacts.get("directory"),
            "visualization": visualization,
            "lifecycle_report": lifecycle_report,
        },
        "profiling": dict(data.get("profiling") or {}),
    }
    return normalized
