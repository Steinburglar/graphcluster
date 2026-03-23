# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Shared pytest fixtures for repository-local toy datasets.

The goal here is to make tests point at a configurable toy dataset without
hard-coding a filename in every test. For now, one default dataset is selected,
but swapping the default later should only require changing this fixture layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest


TESTS_DIR = Path(__file__).resolve().parent
DATA_DIR = TESTS_DIR / "data"
DEFAULT_TOY_DATASET_BASENAME = "Ga80Pt20_129_773K_ss_1.all.bin"


def toy_dataset_path(dataset_name: str | None = None) -> Path:
    """Resolve a toy dataset path under ``tests/data``.

    Args:
        dataset_name: Optional dataset filename. If omitted, use the current
            default toy dataset.

    Returns:
        The resolved path to the requested dataset.

    Raises:
        FileNotFoundError: If the requested dataset cannot be found.
    """
    selected_name = dataset_name or DEFAULT_TOY_DATASET_BASENAME
    matches = sorted(
        path
        for path in DATA_DIR.rglob("*")
        if path.is_file() and path.name == selected_name
    )
    if not matches:
        raise FileNotFoundError(
            f"Could not find toy dataset '{selected_name}' under {DATA_DIR}."
        )
    return matches[0]


@pytest.fixture(scope="session")
def default_toy_dataset() -> Path:
    """Return the repository's current default toy dataset."""
    return toy_dataset_path()


@pytest.fixture
def toy_dataset_factory():
    """Return a helper for resolving named toy datasets under ``tests/data``."""
    return toy_dataset_path
