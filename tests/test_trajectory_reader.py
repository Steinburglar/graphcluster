# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for backend-agnostic trajectory reading."""

from graphcluster.io.ase_source import ASETrajectorySource
from graphcluster.io.trajectory_reader import TrajectoryReader


def test_trajectory_reader_defaults_to_ase_backend(default_toy_dataset) -> None:
    reader = TrajectoryReader(
        trajectory_path=str(default_toy_dataset),
        start=0,
        stop=1,
        stride=1,
    )
    assert reader.backend == "ase"
    assert reader.format == "lammps-dump-binary"
    assert isinstance(reader.source, ASETrajectorySource)


def test_trajectory_reader_reads_first_frame(default_toy_dataset) -> None:
    reader = TrajectoryReader(
        trajectory_path=str(default_toy_dataset),
        start=0,
        stop=1,
        stride=1,
    )
    frame = next(iter(reader))
    assert frame.index == 0
    assert frame.metadata["num_atoms"] == 129
    assert set(frame.atom_types) == {1, 2}
    assert frame.positions.shape == (129, 3)
    assert frame.cell_origin is not None
    assert frame.cell_origin.tolist() == [-29.0, -29.0, -29.0]
    assert frame.chemical_symbols is None


def test_trajectory_reader_resolves_chemical_symbols_from_type_map(
    default_toy_dataset,
) -> None:
    reader = TrajectoryReader.from_config(
        {
            "input": {
                "trajectory": str(default_toy_dataset),
                "backend": "ase",
                "type_map": {1: "Ga", 2: "Pt"},
            },
            "frames": {
                "start": 0,
                "stop": 1,
                "stride": 1,
            },
        }
    )
    frame = next(iter(reader))
    assert frame.chemical_symbols is not None
    assert set(frame.chemical_symbols) == {"Ga", "Pt"}


def test_trajectory_reader_from_config_respects_backend_and_path(default_toy_dataset) -> None:
    reader = TrajectoryReader.from_config(
        {
            "input": {
                "trajectory": str(default_toy_dataset),
                "backend": "ase",
            },
            "frames": {
                "start": 0,
                "stop": 1,
                "stride": 1,
            },
        }
    )
    assert reader.backend == "ase"
    assert reader.trajectory_path == str(default_toy_dataset)
