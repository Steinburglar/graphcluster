#!/usr/bin/env bash
set -euo pipefail

ROOT=/n/home12/lsteinberger
GRAPHCLUSTER=$ROOT/code/graphcluster
OUTDIR=$ROOT/systems/water/analysis/profiling/$(date +%Y%m%d_%H%M%S)_water_profile
MODEL=${1:-/n/home12/lsteinberger/foundation_models/compiled/Allegro-OAM-L-0.1.ase_edges.cuda.cluster.nequip.pt2}

mkdir -p "$OUTDIR"
export MODEL_PATH="$MODEL"

python - << 'PY' | tee "$OUTDIR/preflight.log"
from __future__ import annotations
import json
import os
import platform
import sys

import torch
import nequip
from ase import Atoms
from allegro_annotate import AllegroEdgeEnergyCalculator

model = os.environ.get("MODEL_PATH")
if not model:
    raise RuntimeError("MODEL_PATH env var missing")

info = {
    "python_exe": sys.executable,
    "python_version": sys.version,
    "hostname": platform.node(),
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "cuda_device_count": torch.cuda.device_count(),
    "nequip_version": getattr(nequip, "__version__", "unknown"),
    "model_path": model,
}
print(json.dumps(info, indent=2))

atoms = Atoms(
    symbols=["O", "H", "H"],
    positions=[[0.0, 0.0, 0.0], [0.96, 0.0, 0.0], [-0.24, 0.93, 0.0]],
    cell=[12.0, 12.0, 12.0],
    pbc=True,
)
calc = AllegroEdgeEnergyCalculator.from_compiled_model(
    compile_path=model,
    device="cuda",
    chemical_species_to_atom_type_map=True,
)
atoms.calc = calc
e = atoms.get_potential_energy()
f = atoms.get_forces()
print(json.dumps({"preflight_energy_eV": float(e), "forces_shape": list(f.shape)}, indent=2))
print("PREFLIGHT_OK")
PY

python "$GRAPHCLUSTER/profiling/water/run_water_md_graphcluster_profile.py" \
  --compiled-model "$MODEL" \
  --output-dir "$OUTDIR" \
  --n-atoms 1000 \
  --composition O:333,H:667 \
  --box-a 30.0 \
  --min-dist 1.4 \
  --n-steps 80 \
  --dump-every 1 \
  --device cuda | tee "$OUTDIR/run.log"

echo "Wrote: $OUTDIR/profiling_report.json"
