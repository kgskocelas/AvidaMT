#!/usr/bin/env python3
"""
generate_narrow_bracket_sbatch.py

For seeds where the gap between last non-reverting and first reverting cost
is less than 8, runs every whole integer strictly between the two endpoints.

Output directories: narrow_{final|trans}_<seed>/cost_<N>/

Generates:
    narrow_final.sbatch
    narrow_trans.sbatch

Usage:
    python3 generate_narrow_bracket_sbatch.py
    python3 generate_narrow_bracket_sbatch.py --dry-run
    python3 generate_narrow_bracket_sbatch.py --output /path/to/sbatch/dir
"""

import os
import re
import argparse
import pandas as pd
from pathlib import Path


# ── Configuration ─────────────────────────────────────────────────────────────

EXE              = "/mnt/gs21/scratch/groups/devolab/Avida4/executables-to-copy-into-config/mt_lr_gls"
CHECKPOINT_BASE  = "/mnt/gs21/scratch/groups/devolab/Avida4/base_exp_w_indels/base_exp_w_indels-multi"
BASE_DIR_DEFAULT = "."
MEM              = "10gb"
HOURS_PER_COST   = 6
NARROW_THRESHOLD = 8

WALL_TIME_TIERS_H = [4, 8, 24, 48, 96, 168]


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def whole_integer_costs(last_non, first_rev):
    return list(range(int(last_non) + 1, int(first_rev)))


def estimate_wall_time(n_costs):
    estimated_hours = n_costs * HOURS_PER_COST
    for tier_h in WALL_TIME_TIERS_H:
        if estimated_hours <= tier_h:
            return f"{tier_h}:00:00"
    return f"{WALL_TIME_TIERS_H[-1]}:00:00"


def collect_seed_costs(base_dir):
    seed_costs = {"final": {}, "trans": {}}
    skipped    = []
    wide       = []

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

        gap = first_rev - last_non
        if gap >= NARROW_THRESHOLD:
            wide.append((timepoint, seed, last_non, first_rev))
            continue

        seed_costs[timepoint][seed] = whole_integer_costs(last_non, first_rev)

    if missing:
        print(f"WARNING: {len(missing)} missing/unreadable dat file(s):")
        for m in missing:
            print(f"  {m}")

    return seed_costs, skipped, wide


# ── Sbatch generation ─────────────────────────────────────────────────────────

def write_sbatch(timepoint, seed_costs, base_dir, output_dir):
    timepoint_num = 1 if timepoint == "final" else 0
    array_str = ",".join(str(s) for s in sorted(seed_costs))
    max_costs = max(len(c) for c in seed_costs.values())
    wall_time = estimate_wall_time(max_costs)

    cost_lines = ["declare -A COSTS"]
    for seed in sorted(seed_costs):
        costs_str = " ".join(str(c) for c in seed_costs[seed])
        cost_lines.append(f'COSTS[{seed}]="{costs_str}"')

    fname = Path(output_dir) / f"narrow_{timepoint}.sbatch"

    lines = [
        "#!/bin/bash --login",
        f"#SBATCH --job-name=narrow_{timepoint}",
        "#SBATCH --mail-type=END,FAIL",
        "#SBATCH --mail-user=kgs@msu.edu",
        "#SBATCH --ntasks=1",
        f"#SBATCH --mem={MEM}",
        f"#SBATCH --time={wall_time}",
        f"#SBATCH --output=narrow_{timepoint}_%A_%a.log",
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
        f'    OUTDIR="$BASE_DIR/narrow_{timepoint}_${{SEED}}/cost_${{COST}}"',
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
    return fname, wall_time


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate sbatch files for narrow-bracket seeds.")
    parser.add_argument("base_dir", nargs="?", default=BASE_DIR_DEFAULT)
    parser.add_argument("--output", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Scanning: {args.base_dir}")
    print(f"Narrow bracket threshold: gap < {NARROW_THRESHOLD}")

    seed_costs, skipped, wide = collect_seed_costs(args.base_dir)
    total_narrow = sum(len(v) for v in seed_costs.values())

    if total_narrow == 0:
        print("\nNo narrow-bracket seeds found.")
    else:
        print(f"\n{'Seed':<8} {'Timepoint':<8} {'N costs':>7}  Costs to run")
        print("-" * 60)
        for timepoint in ("final", "trans"):
            for seed in sorted(seed_costs[timepoint]):
                costs = seed_costs[timepoint][seed]
                print(f"{seed:<8} {timepoint:<8} {len(costs):>7}  {costs}")

    if wide:
        print(f"\nWide brackets (skipping — handled by generate_linear_stability_sbatch.py):")
        for timepoint, seed, lo, hi in sorted(wide):
            print(f"  {timepoint}/{seed}: {lo}->{hi}  (gap={hi-lo})")

    if skipped:
        print(f"\nSkipped (no valid bracket):")
        for timepoint, seed, reason in skipped:
            print(f"  {timepoint}/{seed}: {reason}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    if total_narrow == 0:
        print("Nothing to write.")
        return

    os.makedirs(args.output, exist_ok=True)
    written = []
    for timepoint in ("final", "trans"):
        if not seed_costs[timepoint]:
            continue
        fname, wall_time = write_sbatch(timepoint, seed_costs[timepoint],
                                        args.base_dir, args.output)
        n = len(seed_costs[timepoint])
        print(f"  Wrote: {fname.name}  ({n} seed(s), wall time {wall_time})")
        written.append(fname.name)

    print(f"\nTo submit:")
    for fname in written:
        print(f"  sbatch {fname}")


if __name__ == "__main__":
    main()
