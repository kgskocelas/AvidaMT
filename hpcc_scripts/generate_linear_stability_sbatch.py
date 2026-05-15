#!/usr/bin/env python3
"""
generate_linear_stability_sbatch.py

For each seed, finds the stability assay bracket (last non-reverting cost,
first reverting cost) and computes 7 evenly-spaced intermediate costs that
divide the gap into 8 equal chunks. Since every seed gets exactly 7 costs,
all jobs have the same wall time and memory.

Generates two sbatch array files:
    linear_final.sbatch
    linear_trans.sbatch

Output data directories (created at runtime):
    <base_dir>/linear_final_<seed>/cost_<N>/
    <base_dir>/linear_trans_<seed>/cost_<N>/

Usage:
    python3 generate_linear_stability_sbatch.py
    python3 generate_linear_stability_sbatch.py --dry-run
    python3 generate_linear_stability_sbatch.py --output /path/to/sbatch/dir
"""

import os
import re
import argparse
import pandas as pd
from pathlib import Path


# ── Configuration ─────────────────────────────────────────────────────────────

EXE             = "/mnt/gs21/scratch/groups/devolab/Avida4/executables-to-copy-into-config/mt_lr_gls"
CHECKPOINT_BASE = "/mnt/gs21/scratch/groups/devolab/Avida4/base_exp_w_indels/base_exp_w_indels-multi"
BASE_DIR_DEFAULT = "."

N_CHUNKS       = 8
N_COSTS        = N_CHUNKS - 1   # 7
HOURS_PER_COST = 6
WALL_TIME      = f"{N_COSTS * HOURS_PER_COST}:00:00"   # 42:00:00
MEM            = "10gb"


# ── Data helpers ──────────────────────────────────────────────────────────────

def parse_folder_name(name):
    m = re.fullmatch(r"(final|trans)_entrench_(\d+)", name)
    return (m.group(1), int(m.group(2))) if m else None


def load_dat(path):
    try:
        return pd.read_csv(path, sep=r"\s+")
    except Exception:
        return None


def majority_reverted(df, cost):
    rows = df[df["cost"] == cost]
    if rows.empty:
        return None
    return rows["reverted"].sum() > len(rows) / 2


def get_bracket(df):
    costs   = sorted(df["cost"].unique())
    non_rev = [c for c in costs if not majority_reverted(df, c)]
    rev     = [c for c in costs if majority_reverted(df, c)]
    last_non  = max(non_rev) if non_rev else None
    first_rev = min(rev)     if rev     else None

    if   last_non is None and first_rev is not None: reason = "always_reverted"
    elif first_rev is None and last_non is not None: reason = "never_reverted"
    elif last_non is None and first_rev is None:     reason = "no_data"
    elif last_non >= first_rev:                      reason = "inconsistent"
    else:                                            reason = None

    return last_non, first_rev, reason


def intermediate_costs(last_non, first_rev):
    step = (first_rev - last_non) / N_CHUNKS
    return [round(last_non + i * step, 2) for i in range(1, N_CHUNKS)]


def collect_seed_costs(base_dir):
    seed_costs = {"final": {}, "trans": {}}
    skipped    = []

    reason_labels = {
        "always_reverted": "reverted even at cost=1 (genotype too fragile)",
        "never_reverted":  "held on even at cost=2048 (genotype very robust)",
        "no_data":         "dat file empty or unreadable",
        "inconsistent":    "non-monotonic reversion pattern (check raw data)",
    }

    missing = []
    for entry in sorted(os.scandir(base_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        parsed = parse_folder_name(entry.name)
        if not parsed:
            continue
        timepoint, seed = parsed
        dat_path = Path(entry.path) / "lod_entrench_final.dat"
        if not dat_path.exists():
            missing.append(f"{entry.name}/lod_entrench_final.dat")
            continue
        df = load_dat(dat_path)
        if df is None or "cost" not in df.columns or "reverted" not in df.columns:
            missing.append(f"{entry.name}/lod_entrench_final.dat (unreadable)")
            continue

        last_non, first_rev, reason = get_bracket(df)

        if reason is not None:
            skipped.append((timepoint, seed, reason_labels.get(reason, reason)))
            continue

        seed_costs[timepoint][seed] = intermediate_costs(last_non, first_rev)

    if missing:
        print(f"WARNING: {len(missing)} missing/unreadable dat file(s):")
        for m in missing:
            print(f"  {m}")

    return seed_costs, skipped


# ── Sbatch generation ─────────────────────────────────────────────────────────

def write_sbatch(timepoint, seed_costs, base_dir, output_dir):
    timepoint_num = 1 if timepoint == "final" else 0
    array_str = ",".join(str(s) for s in sorted(seed_costs))

    cost_lines = ["declare -A COSTS"]
    for seed in sorted(seed_costs):
        costs_str = " ".join(str(c) for c in seed_costs[seed])
        cost_lines.append(f'COSTS[{seed}]="{costs_str}"')

    fname = Path(output_dir) / f"linear_{timepoint}.sbatch"

    lines = [
        "#!/bin/bash --login",
        f"#SBATCH --job-name=linear_{timepoint}",
        "#SBATCH --mail-type=END,FAIL",
        "#SBATCH --mail-user=kgs@msu.edu",
        "#SBATCH --ntasks=1",
        f"#SBATCH --mem={MEM}",
        f"#SBATCH --time={WALL_TIME}",
        f"#SBATCH --output=linear_{timepoint}_%A_%a.log",
        f"#SBATCH --array={array_str}",
        "",
        "newgrp devolab",
        "umask 0002",
        "set -euo pipefail",
        "",
        "pwd; hostname; date",
        "",
        "SEED=${SLURM_ARRAY_TASK_ID}",
        f"TIMEPOINT={timepoint_num}",
        f"BASE_DIR={base_dir}",
        f"EXE={EXE}",
        f"LOD_BASE={CHECKPOINT_BASE}",
        "BASE_DIR=$(realpath \"$BASE_DIR\")",
        "",
        '[[ -x "$EXE" ]] || { echo "Missing or non-executable $EXE" >&2; exit 1; }',
        "",
        "module purge",
        "module load GCC/13.2.0",
        "module load Boost/1.83.0-GCC-13.2.0",
        "module load util-linux/2.39-GCCcore-13.2.0",
        "",
        "\n".join(cost_lines),
        "",
        f'echo "Seed: $SEED  Timepoint: {timepoint}"',
        "date",
        "",
        'IFS=\' \' read -ra SEED_COSTS <<< "${COSTS[$SEED]}"',
        'for COST in "${SEED_COSTS[@]}"; do',
        f'    OUTDIR="$BASE_DIR/linear_{timepoint}_${{SEED}}/cost_${{COST}}"',
        '    mkdir -p "$OUTDIR"',
        '    cp "$EXE" "$OUTDIR/"',
        '    cd "$OUTDIR"',
        '    [[ -x ./mt_lr_gls ]] || { echo "Failed to copy executable" >&2; exit 1; }',
        '    echo "  Running cost $COST..."',
        '    LOD_DIR="$LOD_BASE/indel_lod_${SEED}"',
        '    ./mt_lr_gls \\',
        '        -l "${LOD_DIR}/checkpoint-1000000.xml.gz" \\',
        "        --analyze lod_entrench_add \\",
        '        --ea.analysis.input.filename "${LOD_DIR}/lod-1000000.xml.gz" \\',
        "        --ea.mt.lod_analysis_reps=3 \\",
        "        --ea.mt.tissue_accretion_add=$COST \\",
        "        --ea.mt.cost_start_update=0 \\",
        "        --ea.mt.lod_timepoint_to_analyze=$TIMEPOINT \\",
        "        --ea.mt.run_single_entrench_cost=1",
        '    rm -f mt_lr_gls',
        "done",
        "",
        'echo "Done."',
        "date",
    ]

    with open(fname, "w") as f:
        f.write("\n".join(lines) + "\n")
    return fname


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate linear-step stability assay sbatch scripts.")
    parser.add_argument("base_dir", nargs="?", default=BASE_DIR_DEFAULT)
    parser.add_argument("--output", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Scanning: {args.base_dir}")
    print(f"Intermediate costs per seed: {N_COSTS}  ({N_CHUNKS} equal chunks per bracket)")
    print(f"Wall time: {WALL_TIME}  ({N_COSTS} costs x {HOURS_PER_COST}h each)")
    print(f"Memory: {MEM}")

    seed_costs, skipped = collect_seed_costs(args.base_dir)

    print(f"\n{'Seed':<8} {'Timepoint':<8} {'Intermediate costs'}")
    print("-" * 72)
    for timepoint in ("final", "trans"):
        for seed in sorted(seed_costs[timepoint]):
            print(f"{seed:<8} {timepoint:<8} {seed_costs[timepoint][seed]}")

    if skipped:
        print(f"\nSkipped (no valid bracket):")
        for timepoint, seed, reason in skipped:
            print(f"  {timepoint}/{seed}: {reason}")

    n_final = len(seed_costs["final"])
    n_trans = len(seed_costs["trans"])
    print(f"\nSeeds: {n_final} final, {n_trans} trans")
    print(f"Total binary calls: {(n_final + n_trans) * N_COSTS}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    os.makedirs(args.output, exist_ok=True)
    written = []
    for timepoint in ("final", "trans"):
        if not seed_costs[timepoint]:
            print(f"No valid seeds for timepoint '{timepoint}' — skipping.")
            continue
        fname = write_sbatch(timepoint, seed_costs[timepoint],
                             args.base_dir, args.output)
        written.append(fname.name)
        print(f"  Wrote: {fname}")

    print(f"\nTo submit:")
    for fname in written:
        print(f"  sbatch {fname}")


if __name__ == "__main__":
    main()
