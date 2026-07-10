#!/usr/bin/env python3
"""
generate_narrow_bracket_sbatch_base_exp.py

Variant of generate_narrow_bracket_sbatch.py configured for Heather's base
experiment (no indels). Reads coarse stability bracket data from 008b and
generates sbatch files that pull LODs from 002.

For seeds where the gap between last non-reverting and first reverting cost
is less than 8, runs every whole integer strictly between the two endpoints.

One SLURM array task per (seed, cost) pair — each task runs a single binary
call. Without --ea.mt.run_single_entrench_cost (unavailable in the simg), the
binary runs the target cost then keeps doubling until >= 4096. Wall time per
task is set to ceil(log2(4096 / min_cost)) * HOURS_PER_COST.

Output directories: narrow_{final|trans}_<seed>/cost_<N>/

Generates:
    narrow_final.sbatch
    narrow_trans.sbatch

Usage:
    # Dry run — confirms brackets are read correctly from 008b, writes nothing
    python3 generate_narrow_bracket_sbatch_base_exp.py --dry-run

    # Generate sbatch files in current directory (defaults already set for base exp)
    python3 generate_narrow_bracket_sbatch_base_exp.py

    # Override where sbatch files are written
    python3 generate_narrow_bracket_sbatch_base_exp.py --output /path/to/sbatch/dir

    # Override any default
    python3 generate_narrow_bracket_sbatch_base_exp.py \
        --scan-dir /mnt/research/devolab/mt/mt_clean/008b \
        --work-dir /mnt/ufs18/nodr/home/kgs/base-exp-linear-stability \
        --output .
"""

import os
import re
import argparse
import pandas as pd
from pathlib import Path


# ── Configuration ─────────────────────────────────────────────────────────────

SIMG            = "/mnt/home/kgs/avidaMT.simg"
SIMG_BIN        = "/research/AvidaMT/bin/clang-linux-9.0.0/release/link-static/mt_lr_gls"
CHECKPOINT_BASE = "/mnt/research/devolab/mt/mt_clean/002"
SCAN_DIR_DEFAULT = "/mnt/research/devolab/mt/mt_clean/008b"
WORK_DIR_DEFAULT = "/mnt/ufs18/nodr/home/kgs/base-exp-linear-stability"

MEM              = "10gb"
HOURS_PER_COST   = 6
WALL_TIME        = f"{int(HOURS_PER_COST * 1.5)}:00:00"   # 1.5x single-cost budget; SLURM kills extra doubling iterations
NARROW_THRESHOLD = 8


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_folder_name(name):
    # Matches plain and all lettered/plus variants, e.g.:
    #   final_entrench_3002
    #   trans_entrench_b_3002
    #   final_entrench_b_plus_3074
    m = re.fullmatch(r"(final|trans)_entrench_(?:[a-z]+_(?:plus_)?)?(\d+)", name)
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

    # Accumulate dat files per (timepoint, seed) across all directory variants
    # (plain + lettered resume dirs like _b_, _c_, _b_plus_, etc.)
    frames = {}   # (timepoint, seed) -> list of DataFrames
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
        key = (timepoint, seed)
        frames.setdefault(key, []).append(df)

    if missing:
        print(f"WARNING: {len(missing)} missing/unreadable dat file(s):")
        for m in missing:
            print(f"  {m}")

    for (timepoint, seed), dfs in sorted(frames.items()):
        combined = pd.concat(dfs, ignore_index=True)
        last_non, first_rev, reason = get_bracket(combined)

        if reason is not None:
            skipped.append((timepoint, seed, reason_labels.get(reason, reason)))
            continue

        gap = first_rev - last_non
        if gap >= NARROW_THRESHOLD:
            wide.append((timepoint, seed, last_non, first_rev))
            continue

        seed_costs[timepoint][seed] = whole_integer_costs(last_non, first_rev)

    return seed_costs, skipped, wide


# ── Sbatch generation ─────────────────────────────────────────────────────────

def write_sbatch(timepoint, seed_costs, work_dir, output_dir):
    timepoint_num = 1 if timepoint == "final" else 0

    # Build flat list of (seed, cost) pairs — one per array task
    pairs = []
    for seed in sorted(seed_costs):
        for cost in seed_costs[seed]:
            pairs.append((seed, cost))

    n = len(pairs)
    array_str = f"0-{n - 1}"

    pair_lines = ["declare -a SEEDS COSTS"]
    for idx, (seed, cost) in enumerate(pairs):
        cost_val = int(cost) if cost == int(cost) else cost
        pair_lines.append(f"SEEDS[{idx}]={seed}")
        pair_lines.append(f"COSTS[{idx}]={cost_val}")

    fname = Path(output_dir) / f"narrow_{timepoint}.sbatch"

    lines = [
        "#!/bin/bash --login",
        f"#SBATCH --job-name=narrow_{timepoint}",
        "#SBATCH --mail-type=END,FAIL",
        "#SBATCH --mail-user=kgs@msu.edu",
        "#SBATCH --ntasks=1",
        f"#SBATCH --mem={MEM}",
        f"#SBATCH --time={WALL_TIME}",
        f"#SBATCH --output=narrow_{timepoint}_%A_%a.log",
        f"#SBATCH --array={array_str}",
        "",
        "newgrp devolab",
        "umask 0002",
        "set -euo pipefail",
        "",
        "pwd; hostname; date",
        "",
        f"BASE_DIR={work_dir}",
        f"SIMG={SIMG}",
        f"LOD_BASE={CHECKPOINT_BASE}",
        f"TIMEPOINT={timepoint_num}",
        "",
        '[[ -f "$SIMG" ]] || { echo "Missing simg: $SIMG" >&2; exit 1; }',
        "",
        "\n".join(pair_lines),
        "",
        "IDX=${SLURM_ARRAY_TASK_ID}",
        'SEED="${SEEDS[$IDX]}"',
        'COST="${COSTS[$IDX]}"',
        "",
        f'echo "Seed: $SEED  Cost: $COST  Timepoint: {timepoint}"',
        "date",
        "",
        f'OUTDIR="$BASE_DIR/narrow_{timepoint}_${{SEED}}/cost_${{COST}}"',
        'mkdir -p "$OUTDIR"',
        'cd "$OUTDIR"',
        'LOD_DIR="$LOD_BASE/a_${SEED}"',
        'singularity exec \\',
        '    --bind /mnt/research:/mnt/research \\',
        '    --bind /mnt/ufs18:/mnt/ufs18 \\',
        '    "$SIMG" \\',
        f'    {SIMG_BIN} \\',
        '    -l "${LOD_DIR}/checkpoint-1000000.xml.gz" \\',
        "    --analyze lod_entrench_add \\",
        '    --ea.analysis.input.filename "${LOD_DIR}/lod-1000000.xml.gz" \\',
        "    --ea.mt.lod_analysis_reps=3 \\",
        "    --ea.mt.tissue_accretion_add=$COST \\",
        "    --ea.mt.cost_start_update=0 \\",
        "    --ea.mt.lod_timepoint_to_analyze=$TIMEPOINT",
        "",
        'echo "Done."',
        "date",
    ]

    with open(fname, "w") as f:
        f.write("\n".join(lines) + "\n")
    return fname, n


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate narrow-bracket sbatch scripts for base experiment (no indels).")
    parser.add_argument("--scan-dir", default=SCAN_DIR_DEFAULT,
                        help="Directory containing 008b coarse stability data to read brackets from")
    parser.add_argument("--work-dir", default=WORK_DIR_DEFAULT,
                        help="nodr directory where sbatch jobs will write output")
    parser.add_argument("--output", default=".",
                        help="Where to write the generated sbatch files")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Scanning brackets from: {args.scan_dir}")
    print(f"Sbatch output (BASE_DIR): {args.work_dir}")
    print(f"Narrow bracket threshold: gap < {NARROW_THRESHOLD}")

    seed_costs, skipped, wide = collect_seed_costs(args.scan_dir)
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
        print(f"\nWide brackets (skipping — handled by generate_linear_stability_sbatch_base_exp.py):")
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
        fname, n_tasks = write_sbatch(timepoint, seed_costs[timepoint],
                                       args.work_dir, args.output)
        print(f"  Wrote: {fname.name}  ({n_tasks} tasks, wall time {WALL_TIME})")
        written.append(fname.name)

    print(f"\nTo submit:")
    for fname in written:
        print(f"  sbatch {fname}")


if __name__ == "__main__":
    main()
