# Date: 2026-03-23
# Requested attribution note: scaffold drafted with AI assistance under direction of Lucas Steinberger.
"""Tests for backend-agnostic trajectory reading."""

from pathlib import Path

from ase import Atoms
from ase.io import write
from ase.io.trajectory import Trajectory

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


def test_trajectory_reader_can_read_xyz_frames(tmp_path: Path) -> None:
    xyz_path = tmp_path / "toy.xyz"
    xyz_path.write_text(
        "\n".join(
            [
                "2",
                "frame 0",
                "Si 0.0 0.0 0.0",
                "O 1.0 0.0 0.0",
                "2",
                "frame 1",
                "Si 0.1 0.0 0.0",
                "O 1.1 0.0 0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    reader = TrajectoryReader(
        trajectory_path=str(xyz_path),
        start=0,
        stop=2,
        stride=1,
    )
    frames = list(reader)

    assert reader.format == "xyz"
    assert len(frames) == 2
    assert frames[0].index == 0
    assert frames[0].positions.shape == (2, 3)
    assert frames[0].atom_types == ["Si", "O"]
    assert frames[0].chemical_symbols == ["Si", "O"]
    assert frames[0].metadata["num_atoms"] == 2


def test_trajectory_reader_preserves_exported_allegro_edge_metadata(tmp_path: Path) -> None:
    traj_path = tmp_path / "allegro_edges.traj"
    atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    atoms.info["allegro_edge_indices"] = [[0, 1], [1, 0]]
    atoms.info["allegro_edge_energies"] = [-0.2, -0.3]
    atoms.info["allegro_edge_lengths"] = [1.0, 1.0]
    write(traj_path, atoms, format="traj")

    reader = TrajectoryReader(
        trajectory_path=str(traj_path),
        start=0,
        stop=1,
        stride=1,
    )
    frame = next(iter(reader))

    assert frame.metadata["ase_info"]["allegro_edge_indices"] == [[0, 1], [1, 0]]
    assert frame.metadata["ase_info"]["allegro_edge_energies"] == [-0.2, -0.3]
    assert frame.metadata["ase_info"]["allegro_edge_lengths"] == [1.0, 1.0]


def test_trajectory_reader_can_infer_and_read_traj_frames(tmp_path: Path) -> None:
    traj_path = tmp_path / "toy.traj"
    atoms0 = Atoms("SiO", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    atoms1 = Atoms("SiO", positions=[[0.1, 0.0, 0.0], [1.1, 0.0, 0.0]])
    with Trajectory(traj_path, mode="w") as trajectory:
        trajectory.write(atoms0)
        trajectory.write(atoms1)

    reader = TrajectoryReader(
        trajectory_path=str(traj_path),
        start=0,
        stop=2,
        stride=1,
    )
    frames = list(reader)

    assert reader.format == "traj"
    assert len(frames) == 2
    assert frames[0].positions.shape == (2, 3)
    assert frames[1].positions[0, 0] == 0.1


def test_trajectory_reader_can_recover_cell_origin_from_reference_trajectory(
    tmp_path: Path,
) -> None:
    annotated_traj_path = tmp_path / "annotated.traj"
    annotated_atoms = Atoms("SiO", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    write(annotated_traj_path, annotated_atoms, format="traj")

    reference_xyz_path = tmp_path / "reference.extxyz"
    reference_atoms = Atoms("SiO", positions=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    reference_atoms.set_cell([5.0, 5.0, 5.0])
    reference_atoms.set_pbc(True)
    reference_atoms.info["cell_origin"] = [-2.0, -2.0, -2.0]
    write(reference_xyz_path, reference_atoms, format="extxyz")

    reader = TrajectoryReader.from_config(
        {
            "input": {
                "trajectory": str(annotated_traj_path),
                "backend": "ase",
                "cell_origin_reference_trajectory": str(reference_xyz_path),
                "cell_origin_reference_format": "extxyz",
            },
            "frames": {
                "start": 0,
                "stop": 1,
                "stride": 1,
            },
        }
    )

    frame = next(iter(reader))
    assert frame.cell_origin is not None
    assert frame.cell_origin.tolist() == [-2.0, -2.0, -2.0]
    assert frame.metadata["reference_metadata"]["cell_origin"] == [-2.0, -2.0, -2.0]
