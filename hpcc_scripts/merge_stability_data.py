#!/usr/bin/env python3
"""
merge_stability_data.py

Produces two merged datasets per seed/timepoint by combining the original
power-of-2 costs with intermediate cost runs, then packages them as tar.gz.

Dataset 1 — "linear": original + linear_{final|trans}_<seed>/cost_<N>/
    Every seed has 7 evenly-spaced intermediate costs (floats ok).

Dataset 2 — "wholenumber": original + best available intermediate costs
    Wide-bracket seeds (gap >= 8): same as dataset 1 (linear float costs)
    Narrow-bracket seeds (gap < 8): narrow_{final|trans}_<seed>/cost_<N>/
                                    (whole integers only)

Output:
    merged_linear.tar.gz      -- linear_final_<seed>.dat, linear_trans_<seed>.dat
    merged_wholenumber.tar.gz -- wholenumber_final_<seed>.dat, wholenumber_trans_<seed>.dat

Usage:
    python3 merge_stability_data.py
    python3 merge_stability_data.py --output /path/to/output/dir
    python3 merge_stability_data.py --dry-run
"""

import os
import re
import tarfile
import tempfile
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


def linear_intermediate_costs(last_non, first_rev):
    step = (first_rev - last_non) / N_CHUNKS
    return [round(last_non + i * step, 2) for i in range(1, N_CHUNKS)]


def narrow_intermediate_costs(last_non, first_rev):
    return list(range(int(last_non) + 1, int(first_rev)))


# ── Data loading ──────────────────────────────────────────────────────────────

def load_cost_dir(base_dir, prefix, timepoint, seed):
    """
    Load and concatenate all lod_entrench_final.dat files from
    <prefix>_{timepoint}_{seed}/cost_*/
    Returns a dataframe or None if directory doesn't exist.
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
        description="Merge stability assay data into two tar.gz datasets.")
    parser.add_argument("base_dir", nargs="?", default=BASE_DIR_DEFAULT)
    parser.add_argument("--output", default=".",
                        help="Directory to write tar.gz files (default: current directory)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be merged without writing files")
    args = parser.parse_args()

    base_dir   = Path(args.base_dir)
    output_dir = Path(args.output)

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
          f"{'Linear costs':>6}  {'Wholenumber costs':>17}")
    print("-" * 72)

    # Build merged dataframes in memory before writing tar
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
                      f"WARNING: narrow_{timepoint}_{seed}/ not found — "
                      f"using linear costs for wholenumber dataset")
                wholenumber_merged = linear_merged
            else:
                wholenumber_merged = (pd.concat([orig_df, narrow_df], ignore_index=True)
                                        .sort_values(["cost", "iteration"])
                                        .reset_index(drop=True))
        else:
            # Wide bracket: wholenumber dataset == linear dataset
            wholenumber_merged = linear_merged

        wholenumber_fname = f"wholenumber_{timepoint}_{seed}.dat"
        wholenumber_files[wholenumber_fname] = wholenumber_merged
        n_wn_costs = wholenumber_merged["cost"].nunique()

        print(f"{seed:<8} {timepoint:<8} {bracket_str:<14} {btype:<8}  "
              f"{n_linear_costs:>6}  {n_wn_costs:>17}")

    if skipped:
        print(f"\nSkipped {len(skipped)} seed(s):")
        for timepoint, seed, reason in skipped:
            print(f"  {timepoint}/{seed}: {reason}")

    print(f"\nDataset 1 (linear):      {len(linear_files)} files")
    print(f"Dataset 2 (wholenumber): {len(wholenumber_files)} files")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    os.makedirs(output_dir, exist_ok=True)

    # ── Write tar.gz files ───────────────────────────────────────────────────
    for archive_name, file_dict in [
        ("merged_linear.tar.gz",      linear_files),
        ("merged_wholenumber.tar.gz", wholenumber_files),
    ]:
        archive_path = output_dir / archive_name
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write each dat file to temp dir, then tar them up
            for fname, df in file_dict.items():
                fpath = Path(tmpdir) / fname
                df.to_csv(fpath, sep="\t", index=False)

            with tarfile.open(archive_path, "w:gz") as tar:
                for fname in sorted(file_dict.keys()):
                    tar.add(Path(tmpdir) / fname, arcname=fname)

        size_mb = archive_path.stat().st_size / 1024 / 1024
        print(f"  Wrote: {archive_path}  ({len(file_dict)} files, {size_mb:.1f} MB)")

    print("\nDone.")


if __name__ == "__main__":
    main()
