# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for toy-dataset resolution in the test suite."""

from __future__ import annotations


def test_default_toy_dataset_exists(default_toy_dataset) -> None:
    assert default_toy_dataset.exists()
    assert default_toy_dataset.is_file()


def test_default_toy_dataset_lives_under_tests_data(default_toy_dataset) -> None:
    parts = default_toy_dataset.parts
    assert "tests" in parts
    assert "data" in parts


def test_toy_dataset_factory_can_resolve_the_current_default(
    toy_dataset_factory,
) -> None:
    dataset_path = toy_dataset_factory("Ga80Pt20_129_773K_ss_1.all.bin")
    assert dataset_path.name == "Ga80Pt20_129_773K_ss_1.all.bin"
