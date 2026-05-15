"""Compatibility shim for the retired inline Allegro annotation module.

Allegro annotation is now a standalone command:

``annotate-allegro --input raw.xyz --compiled-model model.pt2 --output edges.traj``

The ``graphcluster`` runner intentionally no longer imports this module or
switches inputs mid-run.
"""

from __future__ import annotations

from .annotate_allegro_cli import annotate_from_args, build_parser, parse_key_value_args

__all__ = ["annotate_from_args", "build_parser", "parse_key_value_args"]
