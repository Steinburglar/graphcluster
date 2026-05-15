from pathlib import Path

import pytest

from graphcluster.annotate_allegro_cli import annotate_from_args, build_parser, parse_key_value_args


def test_annotate_allegro_cli_passes_explicit_args_to_exporter(tmp_path: Path) -> None:
    calls: list[dict] = []
    output_path = tmp_path / "annotated.traj"
    args = build_parser().parse_args(
        [
            "--input",
            "/tmp/raw.xyz",
            "--compiled-model",
            "/tmp/model.pt2",
            "--output",
            str(output_path),
            "--input-format",
            "xyz",
            "--output-format",
            "traj",
            "--device",
            "cuda",
            "--start",
            "1",
            "--stop",
            "5",
            "--stride",
            "2",
            "--raw-type-map",
            "1=Ga",
            "--species-to-model-type-map",
            "Ga=Ga",
        ]
    )

    def fake_annotate_trajectory(**kwargs):
        calls.append(kwargs)
        return kwargs["output_path"]

    result = annotate_from_args(args, annotate_trajectory_fn=fake_annotate_trajectory)

    assert result == output_path
    assert calls == [
        {
            "compiled_model": "/tmp/model.pt2",
            "input_path": "/tmp/raw.xyz",
            "output_path": str(output_path),
            "input_format": "xyz",
            "output_format": "traj",
            "device": "cuda",
            "start": 1,
            "stop": 5,
            "stride": 2,
            "raw_type_map": {"1": "Ga"},
            "chemical_species_to_atom_type_map": {"Ga": "Ga"},
        }
    ]


def test_annotate_allegro_cli_defaults_species_map_to_auto(tmp_path: Path) -> None:
    calls: list[dict] = []
    args = build_parser().parse_args(
        [
            "--input",
            "/tmp/raw.xyz",
            "--compiled-model",
            "/tmp/model.pt2",
            "--output",
            str(tmp_path / "annotated.traj"),
        ]
    )

    def fake_annotate_trajectory(**kwargs):
        calls.append(kwargs)
        return kwargs["output_path"]

    annotate_from_args(args, annotate_trajectory_fn=fake_annotate_trajectory)

    assert calls[0]["chemical_species_to_atom_type_map"] is True


def test_parse_key_value_args_rejects_malformed_mapping() -> None:
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_key_value_args(["not-a-mapping"])
