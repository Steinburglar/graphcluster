# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Partitioning layer for local and tracked cluster assignments."""

from .partition import Partition
from .partitioner import Partitioner

__all__ = ["Partition", "Partitioner"]
