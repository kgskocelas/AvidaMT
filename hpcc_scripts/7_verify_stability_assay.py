#!/usr/bin/env python3
"""
7_verify_stability_assay.py

Verify lod_entrench_add (stability assay) output for both timepoint conditions
(trans and final).  Run from the directory that contains the trans_entrench_SEED/
and final_entrench_SEED/ subdirectories.

For each seed × timepoint folder, the analysis runs all 12 tissue accretion
costs (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048) sequentially into
the same folder.  Expected output files in each folder:

  lod_entrench_all.dat       data for all LOD individuals across all costs
  lod_entrench_final.dat     timepoint summary (final condition)
  lod_entrench_trans.dat     timepoint summary (trans condition)
  mt_gls.dat                 general GLS stats

The primary completion signal is lod_entrench_all.dat being present, non-empty,
and having data rows.

Seeds are auto-detected by scanning for trans_entrench_<N>/ directories.
Pass --seeds to override (comma-separated, e.g. --seeds 1,2,3).
"""

import os
import re
import sys
import argparse
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

COSTS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

# ── Condition definitions ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Condition:
    name: str           # human label
    dir_prefix: str     # directory = dir_prefix + str(seed)
    log_prefix: str     # log files are named {log_prefix}_JOBID_SEED.log
    tp_file: str        # timepoint-specific dat file expected in every folder


CONDITIONS = [
    Condition("trans", "trans_entrench_", "trans", "lod_entrench_trans.dat"),
    Condition("final", "final_entrench_", "final", "lod_entrench_final.dat"),
]

# Files that must be present and non-empty in every seed folder.
# tp_file is checked separately per condition.
CORE_FILES = [
    "lod_entrench_all.dat",
    "mt_gls.dat",
]

SLURM_ERROR_PATTERNS = [
    (re.compile(r"DUE TO TIME LIMIT",      re.I), "time limit"),
    (re.compile(r"oom.kill|out.of.memory", re.I), "OOM killed"),
    (re.compile(r"\bKilled\b",             re.I), "killed (OOM or admin)"),
    (re.compile(r"CANCELLED",              re.I), "cancelled"),
    (re.compile(r"Segmentation fault",     re.I), "segfault"),
    (re.compile(r"terminate called",       re.I), "crash (terminate called)"),
    (re.compile(r"Aborted",               re.I), "aborted"),
    (re.compile(r"slurmstepd.*error",     re.I), "slurm step error"),
    (re.compile(r"Bus error",             re.I), "bus error"),
    (re.compile(r"std::bad_alloc",        re.I), "bad_alloc (out of memory)"),
]

MAX_WORKERS = None

# ── ANSI colours ──────────────────────────────────────────────────────────────

_USE_COLOR = sys.stdout.isatty()

def _c(code, text): return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def red(t):    return _c("91", t)
def yellow(t): return _c("93", t)
def green(t):  return _c("92", t)
def blue(t):   return _c("94", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)

# ── Detection helpers ─────────────────────────────────────────────────────────

def detect_seeds(base_dir: Path) -> list:
    """Scan base_dir for trans_entrench_<N>/ directories and return sorted seed list."""
    seed_re = re.compile(r"^trans_entrench_(\d+)$")
    seeds = []
    try:
        with os.scandir(base_dir) as it:
            for entry in it:
                if entry.is_dir():
                    m = seed_re.match(entry.name)
                    if m:
                        seeds.append(int(m.group(1)))
    except OSError:
        pass
    return sorted(seeds)

# ── File-reading helpers ──────────────────────────────────────────────────────

def _count_data_lines(path: Path) -> int:
    """Count data lines, skipping blanks, '#' comments, and header lines."""
    try:
        count = 0
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                first = s.split(None, 1)[0]
                if not first.lstrip("-").replace(".", "", 1).isdigit():
                    continue  # header row
                count += 1
        return count
    except OSError:
        return -1

# ── Per-seed check ────────────────────────────────────────────────────────────

def check_seed(seed: int, base_dir: Path, cond: Condition) -> tuple:
    """
    Return (seed, result_dict).

    result_dict keys
    ─────────────────
    status          'complete' | 'incomplete' | 'missing_dir'
    missing_files   list[str]  absent files
    empty_files     list[str]  zero-byte files
    all_dat_rows    int        data row count in lod_entrench_all.dat; -1 = unreadable
    """
    result = {
        "missing_files": [],
        "empty_files":   [],
        "all_dat_rows":  None,
    }

    seed_dir = base_dir / f"{cond.dir_prefix}{seed}"

    if not seed_dir.is_dir():
        result["status"] = "missing_dir"
        return seed, result

    # ── Single scandir pass ───────────────────────────────────────────────────
    file_sizes = {}
    try:
        with os.scandir(seed_dir) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                file_sizes[entry.name] = size
    except PermissionError as exc:
        result["status"] = "incomplete"
        result["missing_files"] = [f"(cannot read directory: {exc})"]
        return seed, result

    # ── Core file checks ──────────────────────────────────────────────────────
    for fname in CORE_FILES + [cond.tp_file]:
        if fname not in file_sizes:
            result["missing_files"].append(fname)
        elif file_sizes[fname] == 0:
            result["empty_files"].append(fname)

    # ── Primary completion signal: lod_entrench_all.dat has data rows ─────────
    all_dat = "lod_entrench_all.dat"
    if all_dat not in result["missing_files"] and file_sizes.get(all_dat, 0) > 0:
        n = _count_data_lines(seed_dir / all_dat)
        result["all_dat_rows"] = n
        if n == 0:
            result["empty_files"].append(f"{all_dat} (0 data rows)")

    # ── Overall status ────────────────────────────────────────────────────────
    failure = result["missing_files"] or result["empty_files"]
    result["status"] = "incomplete" if failure else "complete"
    return seed, result

# ── Slurm log check ───────────────────────────────────────────────────────────

def check_slurm_logs(base_dir: Path, log_prefix: str) -> dict:
    """Return {filename: (seed_or_None, [error_labels])} for error-containing logs."""
    log_issues = {}
    seed_in_name = re.compile(r"_(\d+)\.log$")

    candidates = list(base_dir.glob(f"{log_prefix}_*.log"))
    if not candidates:
        candidates = list(base_dir.glob("*.log"))

    for logfile in candidates:
        m = seed_in_name.search(logfile.name)
        seed = int(m.group(1)) if m else None
        try:
            content = logfile.read_text(errors="replace")
        except OSError:
            continue
        errors_found = [
            label
            for pattern, label in SLURM_ERROR_PATTERNS
            if pattern.search(content)
        ]
        if errors_found:
            log_issues[logfile.name] = (seed, errors_found)
    return log_issues

# ── Output helpers ────────────────────────────────────────────────────────────

def _section(title: str, width: int = 64):
    print()
    print(bold("─" * width))
    print(bold(f"  {title}"))
    print(bold("─" * width))


def _print_condition_results(
    cond: Condition,
    results: dict,
    log_issues: dict,
    base_dir: Path,
    seeds: list,
    no_logs: bool,
):
    complete     = sorted(s for s, r in results.items() if r["status"] == "complete")
    incomplete   = sorted(s for s, r in results.items() if r["status"] == "incomplete")
    missing_dirs = sorted(s for s, r in results.items() if r["status"] == "missing_dir")
    needs_rerun  = sorted(set(missing_dirs) | set(incomplete))
    total        = len(seeds)

    _section(f"CONDITION: {cond.name}")

    # ── Log files ─────────────────────────────────────────────────────────────
    if not no_logs:
        if not log_issues:
            found = list(base_dir.glob(f"{cond.log_prefix}_*.log"))
            if found:
                print(f"  {green('Logs: no errors')} in {len(found)} log file(s).")
            else:
                print(f"  {yellow('Logs: no files found')} matching '{cond.log_prefix}_*.log'")
        else:
            print(f"  {red(bold('Log errors:'))}")
            for logname, (seed, errors) in sorted(log_issues.items()):
                seed_str = (f"seed {seed}" if seed in seeds else f"id {seed}") \
                           if seed else "unknown"
                print(f"    {red('✗')} {bold(logname)}  [{seed_str}]")
                for err in errors:
                    print(f"        {red('→')} {err}")

    # ── Tallies ───────────────────────────────────────────────────────────────
    print(f"  {green(bold('Complete  '))}  {len(complete):>3} / {total}")
    print(f"  {yellow(bold('Incomplete'))}  {len(incomplete):>3} / {total}")
    print(f"  {red(bold('Missing   '))}  {len(missing_dirs):>3} / {total}")

    # ── Missing directories ───────────────────────────────────────────────────
    if missing_dirs:
        print()
        print(f"  {red(bold(f'Missing directories ({len(missing_dirs)} seeds):'))}")
        for s in missing_dirs:
            print(f"    {red(str(s))}  →  {cond.dir_prefix}{s}/  not found")

    # ── Incomplete seeds ──────────────────────────────────────────────────────
    if incomplete:
        print()
        print(f"  {yellow(bold(f'Incomplete seeds ({len(incomplete)} seeds):'))}")
        for seed in incomplete:
            r = results[seed]
            print(f"\n    {bold(yellow(f'Seed {seed}'))}")

            if r["missing_files"]:
                print(f"      {red('✗ Missing files:')}  {', '.join(r['missing_files'])}")
            if r["empty_files"]:
                print(f"      {red('✗ Empty/incomplete files:')}  {', '.join(r['empty_files'])}")

            rows = r["all_dat_rows"]
            if rows is not None and rows > 0:
                print(f"      {blue('ℹ lod_entrench_all.dat:')}  {rows} data rows")

    # ── Re-run array ──────────────────────────────────────────────────────────
    print()
    if not needs_rerun:
        print(f"  {green(bold(f'✓ All {total} seeds complete.'))}")
    else:
        array_str = ','.join(str(s) for s in needs_rerun)
        print(f"  {red(bold(f'{len(needs_rerun)} seed(s) need rerun:'))}")
        print(f"  {bold(yellow(f'#SBATCH --array={array_str}'))}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directory", nargs="?", default=".",
        help="Base directory containing all condition subdirs (default: cwd)",
    )
    parser.add_argument(
        "--condition", "-c",
        choices=[c.name for c in CONDITIONS] + ["all"],
        default="all",
        help="Which condition(s) to check (default: all)",
    )
    parser.add_argument(
        "--seeds",
        default=None,
        help="Comma-separated seed list to check (default: auto-detect from trans_entrench_N/ dirs)",
    )
    parser.add_argument(
        "--workers", type=int, default=MAX_WORKERS,
        help="Parallel worker threads (default: unlimited)",
    )
    parser.add_argument(
        "--no-logs", action="store_true",
        help="Skip slurm log file scan",
    )
    parser.add_argument(
        "--delete-failed", action="store_true",
        help="Delete directories for incomplete seeds after reporting (so they can be cleanly rerun)",
    )

    args = parser.parse_args()

    base_dir = Path(args.directory).resolve()
    target_conditions = CONDITIONS if args.condition == "all" \
                        else [c for c in CONDITIONS if c.name == args.condition]

    if args.seeds:
        seeds = sorted(int(s) for s in args.seeds.split(","))
    else:
        seeds = detect_seeds(base_dir)
        if not seeds:
            print(red("No trans_entrench_<N>/ directories found. "
                      "Run from the experiment directory or pass --seeds."))
            sys.exit(1)

    print(bold(f"Base directory : {base_dir}"))
    print(bold(f"Seeds          : {len(seeds)} detected"))
    print(bold(f"Conditions     : {', '.join(c.name for c in target_conditions)}"))
    print(bold(f"Workers        : {args.workers if args.workers is not None else 'unlimited'}"))

    # ── Collect all results ───────────────────────────────────────────────────
    all_results:     dict[str, dict] = {}
    all_log_issues:  dict[str, dict] = {}
    all_needs_rerun: dict[str, list] = {}

    for cond in target_conditions:
        results: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(check_seed, s, base_dir, cond): s
                for s in seeds
            }
            for future in as_completed(futures):
                seed, result = future.result()
                results[seed] = result

        all_results[cond.name] = results
        all_log_issues[cond.name] = (
            check_slurm_logs(base_dir, cond.log_prefix)
            if not args.no_logs else {}
        )
        all_needs_rerun[cond.name] = sorted(
            s for s, r in results.items()
            if r["status"] in ("incomplete", "missing_dir")
        )

    # ── Seed-set consistency check ────────────────────────────────────────────
    if len(target_conditions) > 1:
        _section("SEED-SET CONSISTENCY CHECK", width=64)
        attempted_sets = {
            cond.name: set(
                s for s, r in all_results[cond.name].items()
                if r["status"] != "missing_dir"
            )
            for cond in target_conditions
        }
        reference_set = next(iter(attempted_sets.values()))
        consistent = all(s == reference_set for s in attempted_sets.values())

        if consistent:
            print(f"  {green(bold('✓'))} Both conditions were run "
                  f"on the same {len(reference_set)} seeds.")
        else:
            print(f"  {red(bold('✗'))} Conditions were not run on the same seed set.")
            all_attempted = sorted(set.union(*attempted_sets.values()))
            for cond in target_conditions:
                missing = sorted(set(all_attempted) - attempted_sets[cond.name])
                if missing:
                    print(f"    {yellow(cond.name)}: missing {len(missing)} seed(s): "
                          f"{','.join(str(s) for s in missing)}")

    # ── Per-condition results ─────────────────────────────────────────────────
    for cond in target_conditions:
        _print_condition_results(
            cond,
            all_results[cond.name],
            all_log_issues[cond.name],
            base_dir,
            seeds,
            args.no_logs,
        )

    # ── Remove failed seed directories ────────────────────────────────────────
    if args.delete_failed:
        _section("REMOVING FAILED SEED DIRECTORIES", width=64)
        to_remove = [
            base_dir / f"{cond.dir_prefix}{seed}"
            for cond in target_conditions
            for seed, r in all_results[cond.name].items()
            if r["status"] == "incomplete"
        ]
        to_remove.sort()
        if not to_remove:
            print(f"  {green('Nothing to remove.')}")
        else:
            total_removed = 0
            for seed_dir in to_remove:
                try:
                    shutil.rmtree(seed_dir)
                    print(f"  {red('✗')} removed  {seed_dir.name}/")
                    total_removed += 1
                except OSError as exc:
                    print(f"  {yellow('⚠')} could not remove {seed_dir.name}/: {exc}")
            print()
            print(f"  Removed {total_removed} director{'y' if total_removed == 1 else 'ies'}.")

        missing_seeds_path = base_dir / "missing_seeds.txt"
        with open(missing_seeds_path, "w") as fh:
            for cond in target_conditions:
                rerun = all_needs_rerun[cond.name]
                fh.write(f"# {cond.name}\n")
                if rerun:
                    fh.write(f"#SBATCH --array={','.join(str(s) for s in rerun)}\n")
                else:
                    fh.write("# (all complete)\n")
                fh.write("\n")
        print(f"  Wrote {bold(str(missing_seeds_path))}")

    # ── Grand summary ─────────────────────────────────────────────────────────
    if len(target_conditions) > 1:
        _section("GRAND SUMMARY — seeds needing rerun per condition", width=64)
        any_failures = False
        for cond in target_conditions:
            rerun = all_needs_rerun[cond.name]
            if rerun:
                any_failures = True
                print(f"  {bold(cond.name)}  ({len(rerun)} seeds):")
                array_str = ','.join(str(s) for s in rerun)
                print(f"    {bold(yellow(f'#SBATCH --array={array_str}'))}")
            else:
                print(f"  {green(bold(cond.name))}: all complete")
        if not any_failures:
            print()
            print(green(bold("  ✓ Both conditions complete across all seeds.")))

    print()


if __name__ == "__main__":
    main()
