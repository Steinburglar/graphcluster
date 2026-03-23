# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Trajectory-level lifecycle analysis results.

In intuitive terms, this is the output of asking trajectory-wide questions
after online tracking has already been done.

Who touches this:
- lifecycle analyzers
- downstream reporting or notebooks

Who this touches:
- nobody directly; it is an analysis result object
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClusterLifecycleReport:
    """Store summary statistics about tracked clusters over time."""

    summary: dict[str, Any] = field(default_factory=dict)
