# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for the project-owned frame object."""

from graphcluster.io.frame import Frame


def test_frame_keeps_atom_type_information() -> None:
    frame = Frame(
        index=7,
        positions=[[0.0, 0.0, 0.0]],
        time=1.5,
        atom_types=["Ga"],
        metadata={"source": "unit-test"},
    )
    assert frame.index == 7
    assert frame.atom_types == ["Ga"]
    assert frame.metadata["source"] == "unit-test"
