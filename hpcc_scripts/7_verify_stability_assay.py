#!/usr/bin/env python3
"""
7_verify_stability_assay.py

Verify lod_entrench_add (stability assay) output for both timepoint conditions
(trans and final).  Run from the directory that contains the trans_entrench_SEED/
and final_entrench_SEED/ subdirectories.

Each seed x timepoint folder contains the output from a single mt_lr_gls call
that internally loops through all 12 costs (1->2048):

  {tp}_entrench_{seed}/
      lod_entrench_all.dat
      lod_entrench_final.dat   (or lod_entrench_trans.dat)
      mt_gls.dat

Seeds are auto-detected by scanning for trans_entrench_<N>/ directories.
Pass --seeds to override (comma-separated, e.g. --seeds 1,2,3).

If a seed timed out mid-run, its dat files will be partial. Resubmit that
seed at a higher starting cost in a new directory, then concatenate dat files
before running this script.
"""

import os
import re
import sys
import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

COSTS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

# Condition definitions

@dataclass(frozen=True)
class Condition:
    name: str           # human label
    dir_prefix: str     # directory = dir_prefix + str(seed)
    log_prefix: str     # log files named {log_prefix}_*.log
    tp_file: str        # timepoint-specific dat file expected in seed folder


CONDITIONS = [
    Condition("trans", "trans_entrench_", "trans", "lod_entrench_trans.dat"),
    Condition("final", "final_entrench_", "final", "lod_entrench_final.dat"),
]

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

# ANSI colours
_USE_COLOR = sys.stdout.isatty()
def _c(code, text): return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text
def red(t):    return _c("91", t)
def yellow(t): return _c("93", t)
def green(t):  return _c("92", t)
def blue(t):   return _c("94", t)
def bold(t):   return _c("1",  t)


def detect_seeds(base_dir: Path) -> list:
    """Scan base_dir for trans_entrench_<N>/ directories."""
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


def _count_data_lines(path: Path) -> int:
    """Count non-header, non-blank, non-comment lines."""
    try:
        count = 0
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                first = s.split(None, 1)[0]
                if not first.lstrip("-").replace(".", "", 1).isdigit():
                    continue
                count += 1
        return count
    except OSError:
        return -1


def _count_costs_in_dat(path: Path) -> set:
    """Return the set of cost values present in a dat file (first column)."""
    costs = set()
    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split()
                if not parts:
                    continue
                try:
                    val = int(parts[0])
                    if val in COSTS:
                        costs.add(val)
                except ValueError:
                    pass
    except OSError:
        pass
    return costs


def check_seed(seed: int, base_dir: Path, cond: Condition) -> tuple:
    """
    Return (seed, result_dict).

    result_dict keys:
      status         'complete' | 'incomplete' | 'missing_dir'
      missing_files  list[str]
      empty_files    list[str]
      all_dat_rows   int or None
      costs_found    set[int]   costs present in lod_entrench_all.dat
    """
    result = {
        "missing_files": [],
        "empty_files":   [],
        "all_dat_rows":  None,
        "costs_found":   set(),
    }

    seed_dir = base_dir / f"{cond.dir_prefix}{seed}"

    if not seed_dir.is_dir():
        result["status"] = "missing_dir"
        return seed, result

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

    for fname in CORE_FILES + [cond.tp_file]:
        if fname not in file_sizes:
            result["missing_files"].append(fname)
        elif file_sizes[fname] == 0:
            result["empty_files"].append(fname)

    all_dat = "lod_entrench_all.dat"
    if all_dat not in result["missing_files"] and file_sizes.get(all_dat, 0) > 0:
        n = _count_data_lines(seed_dir / all_dat)
        result["all_dat_rows"] = n
        if n == 0:
            result["empty_files"].append(f"{all_dat} (0 data rows)")
        else:
            result["costs_found"] = _count_costs_in_dat(seed_dir / all_dat)
            missing_costs = set(COSTS) - result["costs_found"]
            if missing_costs:
                result["empty_files"].append(
                    f"{all_dat} missing costs: "
                    + ", ".join(str(c) for c in sorted(missing_costs))
                )

    result["status"] = "incomplete" if (result["missing_files"] or result["empty_files"]) else "complete"
    return seed, result


def check_slurm_logs(base_dir: Path, log_prefix: str) -> dict:
    """Return {filename: (seed, [error_labels])} for logs containing errors."""
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
        errors_found = [label for pat, label in SLURM_ERROR_PATTERNS if pat.search(content)]
        if errors_found:
            log_issues[logfile.name] = (seed, errors_found)
    return log_issues


def _section(title: str, width: int = 64):
    print()
    print(bold("─" * width))
    print(bold(f"  {title}"))
    print(bold("─" * width))


def _print_condition_results(cond, results, log_issues, base_dir, seeds, no_logs):
    complete     = sorted(s for s, r in results.items() if r["status"] == "complete")
    incomplete   = sorted(s for s, r in results.items() if r["status"] == "incomplete")
    missing_dirs = sorted(s for s, r in results.items() if r["status"] == "missing_dir")
    needs_rerun  = sorted(set(missing_dirs) | set(incomplete))
    total        = len(seeds)

    _section(f"CONDITION: {cond.name}")

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
                seed_str = (f"seed {seed}" if seed in seeds else f"id {seed}") if seed else "unknown"
                print(f"    {red('x')} {bold(logname)}  [{seed_str}]")
                for err in errors:
                    print(f"        {red('>')} {err}")

    print(f"  {green(bold('Complete  '))}  {len(complete):>3} / {total}")
    print(f"  {yellow(bold('Incomplete'))}  {len(incomplete):>3} / {total}")
    print(f"  {red(bold('Missing   '))}  {len(missing_dirs):>3} / {total}")

    if missing_dirs:
        print()
        print(f"  {red(bold(f'Missing directories ({len(missing_dirs)} seeds):'))}")
        for s in missing_dirs:
            print(f"    {red(str(s))}  ->  {cond.dir_prefix}{s}/  not found")

    if incomplete:
        print()
        print(f"  {yellow(bold(f'Incomplete seeds ({len(incomplete)} seeds):'))}")
        for seed in incomplete:
            r = results[seed]
            costs_done = sorted(r["costs_found"])
            missing_costs = sorted(set(COSTS) - r["costs_found"])
            print(f"\n    {bold(yellow(f'Seed {seed}'))}")
            if r["missing_files"]:
                print(f"      {red('x Missing files:')}  {', '.join(r['missing_files'])}")
            if r["empty_files"]:
                print(f"      {red('x Empty/incomplete:')}")
                for ef in r["empty_files"]:
                    print(f"          {ef}")
            if costs_done:
                print(f"      {blue('Costs present:')}  {', '.join(str(c) for c in costs_done)}")
            if missing_costs:
                resume_cost = missing_costs[0]
                print(f"      {yellow('To resume:')}  --ea.mt.tissue_accretion_add={resume_cost}")

    print()
    if not needs_rerun:
        print(f"  {green(bold(f'All {total} seeds complete.'))}")
    else:
        array_str = ','.join(str(s) for s in needs_rerun)
        print(f"  {red(bold(f'{len(needs_rerun)} seed(s) need rerun:'))}")
        print(f"  {bold(yellow(f'#SBATCH --array={array_str}'))}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="Base directory (default: cwd)")
    parser.add_argument("--condition", "-c",
                        choices=[c.name for c in CONDITIONS] + ["all"], default="all")
    parser.add_argument("--seeds", default=None,
                        help="Comma-separated seed list (default: auto-detect)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--no-logs", action="store_true", help="Skip slurm log scan")
    parser.add_argument("--delete-failed", action="store_true",
                        help="Delete incomplete seed directories after reporting")

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

    all_results:     dict = {}
    all_log_issues:  dict = {}
    all_needs_rerun: dict = {}

    for cond in target_conditions:
        results: dict = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(check_seed, s, base_dir, cond): s for s in seeds}
            for future in as_completed(futures):
                seed, result = future.result()
                results[seed] = result
        all_results[cond.name] = results
        all_log_issues[cond.name] = (
            check_slurm_logs(base_dir, cond.log_prefix) if not args.no_logs else {}
        )
        all_needs_rerun[cond.name] = sorted(
            s for s, r in results.items() if r["status"] in ("incomplete", "missing_dir")
        )

    if len(target_conditions) > 1:
        _section("SEED-SET CONSISTENCY CHECK", width=64)
        attempted_sets = {
            cond.name: set(s for s, r in all_results[cond.name].items()
                           if r["status"] != "missing_dir")
            for cond in target_conditions
        }
        reference_set = next(iter(attempted_sets.values()))
        consistent = all(s == reference_set for s in attempted_sets.values())
        if consistent:
            print(f"  {green(bold('x'))} Both conditions ran on the same {len(reference_set)} seeds.")
        else:
            print(f"  {red(bold('x'))} Conditions were not run on the same seed set.")
            all_attempted = sorted(set.union(*attempted_sets.values()))
            for cond in target_conditions:
                missing = sorted(set(all_attempted) - attempted_sets[cond.name])
                if missing:
                    print(f"    {yellow(cond.name)}: missing {len(missing)} seed(s): "
                          f"{','.join(str(s) for s in missing)}")

    for cond in target_conditions:
        _print_condition_results(
            cond, all_results[cond.name], all_log_issues[cond.name],
            base_dir, seeds, args.no_logs,
        )

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
                    print(f"  {red('x')} removed  {seed_dir.name}/")
                    total_removed += 1
                except OSError as exc:
                    print(f"  " + yellow("!") + f" could not remove {seed_dir.name}/: {exc}")
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

    if len(target_conditions) > 1:
        _section("GRAND SUMMARY", width=64)
        any_failures = False
        for cond in target_conditions:
            rerun = all_needs_rerun[cond.name]
            if rerun:
                any_failures = True
                array_str = ','.join(str(s) for s in rerun)
                print(f"  {bold(cond.name)}  ({len(rerun)} seeds):")
                print(f"    {bold(yellow(f'#SBATCH --array={array_str}'))}")
            else:
                print(f"  {green(bold(cond.name))}: all complete")
        if not any_failures:
            print()
            print(green(bold("  All conditions complete across all seeds.")))

    print()


if __name__ == "__main__":
    main()
