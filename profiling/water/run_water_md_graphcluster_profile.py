#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ase import Atoms, units
from ase.io import write
from ase.md.langevin import Langevin
from ase.md.velocitydistribution import MaxwellBoltzmannDistribution, Stationary, ZeroRotation
import numpy as np

from allegro_annotate import (
    AllegroEdgeEnergyCalculator,
    EdgeEnergyDynamicsObserver,
    EdgeEnergyTrajectoryWriter,
)
from graphcluster.runner import TrajectoryPartitionRunner


def _random_positions_with_min_distance(
    n_atoms: int, box_a: float, seed: int, min_dist: float
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    positions: list[np.ndarray] = []
    max_tries = 20000
    for _ in range(n_atoms):
        placed = False
        for _try in range(max_tries):
            cand = rng.uniform(0.0, box_a, size=(3,))
            if not positions:
                positions.append(cand)
                placed = True
                break
            d2 = np.sum((np.asarray(positions) - cand) ** 2, axis=1)
            if float(np.min(d2)) >= min_dist * min_dist:
                positions.append(cand)
                placed = True
                break
        if not placed:
            raise RuntimeError(
                f"could not place atom with min_dist={min_dist} in box {box_a} A; increase --box-a"
            )
    return np.asarray(positions)


def build_composition_box(
    n_atoms: int, box_a: float, seed: int, composition: str, min_dist: float
) -> Atoms:
    rng = np.random.default_rng(seed)
    symbols: list[str] = []
    for item in composition.split(","):
        specie, count = item.split(":")
        symbols.extend([specie.strip()] * int(count))
    if len(symbols) == 0:
        raise ValueError("composition produced zero atoms")
    if len(symbols) != n_atoms:
        raise ValueError(
            f"composition atom count ({len(symbols)}) != --n-atoms ({n_atoms}). "
            "Set both consistently."
        )
    total = n_atoms
    positions = _random_positions_with_min_distance(total, box_a, seed, min_dist)
    atoms = Atoms(symbols=symbols, positions=positions, cell=[box_a, box_a, box_a], pbc=True)
    return atoms


def run_md(
    atoms: Atoms,
    compiled_model: str,
    device: str,
    n_steps: int,
    dt_fs: float,
    temp_k: float,
    friction: float,
    dump_every: int,
    output_traj: Path,
    annotate_edges: bool,
) -> dict[str, float | int | str]:
    calc = AllegroEdgeEnergyCalculator.from_compiled_model(
        compile_path=compiled_model,
        device=device,
        chemical_species_to_atom_type_map=True,
    )
    atoms.calc = calc

    MaxwellBoltzmannDistribution(atoms, temperature_K=temp_k)
    Stationary(atoms)
    ZeroRotation(atoms)

    dyn = Langevin(
        atoms,
        timestep=dt_fs * units.fs,
        temperature_K=temp_k,
        friction=friction,
    )

    writer = EdgeEnergyTrajectoryWriter(output_path=str(output_traj))
    if annotate_edges:
        observer = EdgeEnergyDynamicsObserver(atoms=atoms, writer=writer)
        observer.attach(dyn, interval=dump_every)
    else:
        dyn.attach(lambda: writer.write(atoms), interval=dump_every)

    start = time.perf_counter()
    dyn.run(n_steps)
    elapsed = time.perf_counter() - start
    return {
        "elapsed_s": elapsed,
        "steps": n_steps,
        "steps_per_s": n_steps / elapsed if elapsed > 0 else 0.0,
        "annotate_edges": annotate_edges,
        "output_traj": str(output_traj),
    }


def write_graphcluster_config(input_traj: Path, output_dir: Path, cutoff: float) -> Path:
    cfg = output_dir / "graphcluster_profile.yaml"
    cfg.write_text(
        "\n".join(
            [
                "source:",
                "  backend: ase",
                "  format: traj",
                f"  path: {input_traj}",
                "selection:",
                "  start: 0",
                "  stop: null",
                "  stride: 1",
                "edges:",
                "  kind: allegro",
                "  energy_field: raw",
                "  energy_to_weight: abs_negative_sum",
                "partition:",
                "  algorithm: leiden",
                "  objective: cpm",
                "  resolution: 0.08",
                "  warm_start: true",
                "tracking:",
                "  method: overlap",
                "analysis:",
                "  enabled: false",
                "visualization:",
                "  enabled: false",
                "profiling:",
                "  enabled: true",
                "",
            ]
        )
    )
    return cfg


def run_graphcluster_profile(config_path: Path) -> dict[str, float | int]:
    runner = TrajectoryPartitionRunner.from_config_path(config_path)
    result = runner.run(progress=True, profile=True)
    timings = dict(result.run_timings)
    timings["frames_processed"] = result.frames_processed
    return timings


def estimate_sync_overhead(md_plain_s: float, md_with_cluster_s: float) -> dict[str, float]:
    slowdown = md_with_cluster_s / md_plain_s if md_plain_s > 0 else float("inf")
    overhead_pct = (slowdown - 1.0) * 100.0
    return {"slowdown_x": slowdown, "overhead_pct": overhead_pct}


def main() -> None:
    p = argparse.ArgumentParser(description="Profile MD vs MD+graphcluster overhead.")
    p.add_argument("--compiled-model", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--n-atoms", type=int, default=1000)
    p.add_argument("--box-a", type=float, default=30.0)
    p.add_argument("--n-steps", type=int, default=200)
    p.add_argument("--dt-fs", type=float, default=0.5)
    p.add_argument("--temperature-k", type=float, default=300.0)
    p.add_argument("--friction", type=float, default=0.01)
    p.add_argument("--dump-every", type=int, default=1)
    p.add_argument("--device", default="cuda")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--min-dist", type=float, default=1.4)
    p.add_argument(
        "--composition",
        default="Pt:333,H:667",
        help=(
            "Comma-separated species counts, ex: O:333,H:667 or Pt:333,H:667. "
            "Must sum to --n-atoms."
        ),
    )
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    atoms0 = build_composition_box(
        args.n_atoms, args.box_a, args.seed, args.composition, args.min_dist
    )
    write(out / "initial_structure.xyz", atoms0)

    md_plain = run_md(
        atoms=atoms0.copy(),
        compiled_model=args.compiled_model,
        device=args.device,
        n_steps=args.n_steps,
        dt_fs=args.dt_fs,
        temp_k=args.temperature_k,
        friction=args.friction,
        dump_every=args.dump_every,
        output_traj=out / "md_plain.traj",
        annotate_edges=False,
    )

    md_edges = run_md(
        atoms=atoms0.copy(),
        compiled_model=args.compiled_model,
        device=args.device,
        n_steps=args.n_steps,
        dt_fs=args.dt_fs,
        temp_k=args.temperature_k,
        friction=args.friction,
        dump_every=args.dump_every,
        output_traj=out / "md_with_edges.traj",
        annotate_edges=True,
    )

    cfg = write_graphcluster_config(out / "md_with_edges.traj", out, cutoff=3.5)
    gc_timings = run_graphcluster_profile(cfg)

    frames = int(gc_timings.get("frames_processed", 0))
    graphcluster_s_per_frame = gc_timings["run_total"] / frames if frames > 0 else 0.0
    md_plain_s_per_step = md_plain["elapsed_s"] / args.n_steps
    est_md_plus_cluster_s = md_edges["elapsed_s"] + (graphcluster_s_per_frame * args.n_steps)
    sync_est = estimate_sync_overhead(md_plain["elapsed_s"], est_md_plus_cluster_s)

    report = {
        "inputs": vars(args),
        "md_plain": md_plain,
        "md_with_edge_export": md_edges,
        "graphcluster_profile": gc_timings,
        "derived": {
            "md_plain_s_per_step": md_plain_s_per_step,
            "graphcluster_s_per_frame": graphcluster_s_per_frame,
            "estimated_sync_md_plus_cluster_s": est_md_plus_cluster_s,
            **sync_est,
        },
    }
    report_path = out / "profiling_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
