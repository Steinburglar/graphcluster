#!/usr/bin/env bash
#SBATCH -J water_gc_profile
#SBATCH -p gpu_test
#SBATCH --gres=gpu:1
#SBATCH --constraint=avx512
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH -t 04:00:00
#SBATCH -o /n/home12/lsteinberger/systems/water/analysis/profiling/slurm-%j.out
#SBATCH -e /n/home12/lsteinberger/systems/water/analysis/profiling/slurm-%j.err

set -euo pipefail

if ! command -v module >/dev/null 2>&1; then
  for init in /usr/share/Modules/init/bash /etc/profile.d/modules.sh; do
    if [[ -f "$init" ]]; then
      # shellcheck disable=SC1090
      source "$init"
      break
    fi
  done
fi

if command -v module >/dev/null 2>&1; then
  module purge
  module load gcc/12.2.0-fasrc01
  module load cuda/12.4.1-fasrc01
  module load python
else
  echo "ERROR: environment modules command not available on this node."
  exit 2
fi

if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
elif [[ -f /n/sw/Miniforge3-26.1.0-0/etc/profile.d/conda.sh ]]; then
  # shellcheck disable=SC1091
  source /n/sw/Miniforge3-26.1.0-0/etc/profile.d/conda.sh
else
  echo "ERROR: conda command/init not available on this node."
  exit 3
fi

mamba activate nequip311

bash /n/home12/lsteinberger/code/graphcluster/profiling/water/run_profile_gpu.sh "$@"
