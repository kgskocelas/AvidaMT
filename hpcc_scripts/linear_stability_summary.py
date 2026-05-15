#!/usr/bin/env python3
"""
linear_stability_summary.py

Scans stability assay result folders and produces a CSV with:
    seed, timepoint, last_non_reverting, first_reverting, intermediate_costs

intermediate_costs is a comma-separated list with no spaces e.g. [144,160,176,192,208,224,240]

Usage:
    python3 linear_stability_summary.py <base_dir>
    python3 linear_stability_summary.py <base_dir> --output my_summary.csv
"""

import os
import re
import argparse
import pandas as pd
from pathlib import Path


BASE_DIR_DEFAULT = "."
N_CHUNKS = 8


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
    else:                                            reason = None

    return last_non, first_rev, reason


def intermediate_costs(last_non, first_rev):
    step = (first_rev - last_non) / N_CHUNKS
    return [round(last_non + i * step, 2) for i in range(1, N_CHUNKS)]


def main():
    parser = argparse.ArgumentParser(description="Generate linear stability bracket summary CSV.")
    parser.add_argument("base_dir", nargs="?", default=BASE_DIR_DEFAULT)
    parser.add_argument("--output", default="linear_stability_summary.csv")
    args = parser.parse_args()

    rows = []
    skipped = []

    for entry in sorted(os.scandir(args.base_dir), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        parsed = parse_folder_name(entry.name)
        if not parsed:
            continue
        timepoint, seed = parsed
        dat_path = Path(entry.path) / "lod_entrench_final.dat"
        if not dat_path.exists():
            skipped.append(f"{entry.name}: lod_entrench_final.dat not found")
            continue
        df = load_dat(dat_path)
        if df is None or "cost" not in df.columns or "reverted" not in df.columns:
            skipped.append(f"{entry.name}: unreadable dat file")
            continue

        last_non, first_rev, reason = get_bracket(df)

        if reason is not None:
            skipped.append(f"{timepoint}/{seed}: {reason}")
            continue

        costs = intermediate_costs(last_non, first_rev)
        costs_str = "[" + ",".join(str(c) for c in costs) + "]"

        rows.append({
            "seed":               seed,
            "timepoint":          timepoint,
            "last_non_reverting": last_non,
            "first_reverting":    first_rev,
            "costs_to_run":       costs_str,
        })

    if skipped:
        print(f"Skipped {len(skipped)} seed(s):")
        for s in skipped:
            print(f"  {s}")

    if not rows:
        print("No valid seeds found.")
        return

    df_out = (pd.DataFrame(rows, columns=["seed", "timepoint",
                                           "last_non_reverting",
                                           "first_reverting",
                                           "costs_to_run"])
                .sort_values(["timepoint", "seed"])
                .reset_index(drop=True))

    df_out.to_csv(args.output, index=False)
    print(f"Wrote {len(df_out)} rows to {args.output}")
    print(df_out.to_string(index=False))


if __name__ == "__main__":
    main()
