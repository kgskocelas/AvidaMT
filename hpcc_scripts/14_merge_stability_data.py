#!/usr/bin/env python3
"""
14_merge_stability_data.py

Produces two merged datasets per seed/timepoint by combining the original
power-of-2 costs with intermediate cost runs. Run from the experiment
directory. Source folders are never modified; merged output is written to
new files.

Expected directory structure (flat, before script 15 reorganizes):
    final_entrench_<seed>/lod_entrench_final.dat
    trans_entrench_<seed>/lod_entrench_final.dat
    linear_{final|trans}_<seed>/cost_<N>/lod_entrench_final.dat
    narrow_{final|trans}_<seed>/cost_<N>/lod_entrench_final.dat

Dataset 1 — "linear": original + linear_{final|trans}_<seed>/cost_<N>/
    Every seed has 7 evenly-spaced intermediate costs (floats ok).

Dataset 2 — "wholenumber": original + best available intermediate costs
    Wide-bracket seeds (gap >= 8): same as dataset 1 (linear float costs)
    Narrow-bracket seeds (gap < 8): narrow_{final|trans}_<seed>/cost_<N>/
                                    (whole integers only)

Output:
    merged/linear/linear_{final|trans}_<seed>.dat
    merged/wholenumber/wholenumber_{final|trans}_<seed>.dat

Usage:
    python3 14_merge_stability_data.py
    python3 14_merge_stability_data.py --dry-run
"""

import os
import re
import argparse
import pandas as pd
from pathlib import Path


BASE_DIR_DEFAULT = "."
N_CHUNKS         = 8
NARROW_THRESHOLD = 8


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_original_folder(name):
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


# ── Data loading ──────────────────────────────────────────────────────────────

def load_cost_dir(base_dir, prefix, timepoint, seed):
    """
    Load and concatenate all lod_entrench_final.dat files from
    <prefix>_{timepoint}_{seed}/cost_*/
    """
    cost_root = Path(base_dir) / f"{prefix}_{timepoint}_{seed}"
    if not cost_root.exists():
        return None

    frames = []
    for entry in sorted(os.scandir(cost_root), key=lambda e: e.name):
        if not entry.is_dir() or not re.fullmatch(r"cost_.+", entry.name):
            continue
        dat_path = Path(entry.path) / "lod_entrench_final.dat"
        df = load_dat(dat_path)
        if df is not None:
            frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Merge stability assay data into two datasets.")
    parser.add_argument("base_dir", nargs="?", default=BASE_DIR_DEFAULT)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be merged without writing files")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)

    # Collect all original seeds
    seeds = []
    for entry in sorted(os.scandir(base_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        parsed = parse_original_folder(entry.name)
        if not parsed:
            continue
        timepoint, seed = parsed
        dat_path = Path(entry.path) / "lod_entrench_final.dat"
        if not dat_path.exists():
            continue
        df = load_dat(dat_path)
        if df is None or "cost" not in df.columns or "reverted" not in df.columns:
            continue
        last_non, first_rev, reason = get_bracket(df)
        seeds.append((timepoint, seed, df, last_non, first_rev, reason))

    if not seeds:
        print("No original seed folders found.")
        return

    print(f"Found {len(seeds)} seed/timepoint combinations")
    print(f"\n{'Seed':<8} {'Timepoint':<8} {'Bracket':<14} {'Type':<8}  "
          f"{'Linear costs':>12}  {'Wholenumber costs':>17}")
    print("-" * 76)

    linear_files      = {}   # filename -> dataframe
    wholenumber_files = {}
    skipped = []

    for timepoint, seed, orig_df, last_non, first_rev, reason in seeds:
        if reason is not None:
            skipped.append((timepoint, seed, reason))
            print(f"{seed:<8} {timepoint:<8} {'N/A':<14} {'SKIP':<8}  {reason}")
            continue

        gap = first_rev - last_non
        is_narrow = gap < NARROW_THRESHOLD
        bracket_str = f"{last_non}->{first_rev}"
        btype = "narrow" if is_narrow else "wide"

        # ── Load linear intermediate data ─────────────────────────────────────
        linear_df = load_cost_dir(base_dir, "linear", timepoint, seed)
        if linear_df is None:
            print(f"{seed:<8} {timepoint:<8} {bracket_str:<14} {btype:<8}  "
                  f"WARNING: linear_{timepoint}_{seed}/ not found — skipping")
            skipped.append((timepoint, seed, f"linear_{timepoint}_{seed}/ missing"))
            continue

        # ── Dataset 1: original + linear (floats) ────────────────────────────
        linear_merged = (pd.concat([orig_df, linear_df], ignore_index=True)
                           .sort_values(["cost", "iteration"])
                           .reset_index(drop=True))
        linear_fname = f"linear_{timepoint}_{seed}.dat"
        linear_files[linear_fname] = linear_merged
        n_linear_costs = linear_merged["cost"].nunique()

        # ── Dataset 2: original + wholenumber ────────────────────────────────
        if is_narrow:
            narrow_df = load_cost_dir(base_dir, "narrow", timepoint, seed)
            if narrow_df is None:
                print(f"{seed:<8} {timepoint:<8} {bracket_str:<14} {btype:<8}  "
                      f"{n_linear_costs:>12}  {'(skipped-no narrow)':>17}")
                skipped.append((timepoint, seed, f"narrow_{timepoint}_{seed}/ missing"))
                continue
            wholenumber_merged = (pd.concat([orig_df, narrow_df], ignore_index=True)
                                    .sort_values(["cost", "iteration"])
                                    .reset_index(drop=True))
        else:
            wholenumber_merged = linear_merged

        wholenumber_fname = f"wholenumber_{timepoint}_{seed}.dat"
        wholenumber_files[wholenumber_fname] = wholenumber_merged
        n_wn_costs = wholenumber_merged["cost"].nunique()

        print(f"{seed:<8} {timepoint:<8} {bracket_str:<14} {btype:<8}  "
              f"{n_linear_costs:>12}  {n_wn_costs:>17}")

    if skipped:
        print(f"\nSkipped {len(skipped)} seed(s):")
        for timepoint, seed, reason in skipped:
            print(f"  {timepoint}/{seed}: {reason}")

    print(f"\nDataset 1 (linear):      {len(linear_files)} files")
    print(f"Dataset 2 (wholenumber): {len(wholenumber_files)} files")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    # ── Write merged .dat files ───────────────────────────────────────────────
    linear_out      = base_dir / "merged" / "linear"
    wholenumber_out = base_dir / "merged" / "wholenumber"
    os.makedirs(linear_out,      exist_ok=True)
    os.makedirs(wholenumber_out, exist_ok=True)

    for fname, df in sorted(linear_files.items()):
        fpath = linear_out / fname
        df.to_csv(fpath, sep="\t", index=False)
        print(f"  Wrote: {fpath}")

    for fname, df in sorted(wholenumber_files.items()):
        fpath = wholenumber_out / fname
        df.to_csv(fpath, sep="\t", index=False)
        print(f"  Wrote: {fpath}")

    print("\nDone.")


if __name__ == "__main__":
    main()
