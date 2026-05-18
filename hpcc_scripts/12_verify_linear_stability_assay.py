#!/usr/bin/env python3
"""
verify_linear_stability_assay.py

Verify output for the linear-step stability assay.  Each seed's SLURM job
runs 7 seed-specific costs in sequence, one binary call per cost.

Expected directory structure:
    <base_dir>/
        linear_final_<seed>/
            cost_<N>/
                lod_entrench_all.dat
                lod_entrench_final.dat
                mt_gls.dat
        linear_trans_<seed>/
            cost_<N>/  ...
        linear_final_<JOBID>_<seed>.log
        linear_trans_<JOBID>_<seed>.log

Seeds are auto-detected by scanning for linear_final_<N>/ or
linear_trans_<N>/ directories.  Pass --seeds to override.

Usage:
    python3 verify_linear_stability_assay.py [directory]
    python3 verify_linear_stability_assay.py [directory] --condition final
    python3 verify_linear_stability_assay.py [directory] --seeds 1007,1008,...
"""

import os
import re
import sys
import argparse
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PREFIX = "linear"
N_COSTS_EXPECTED = 7

COST_FILES = [
    "lod_entrench_all.dat",
    "lod_entrench_final.dat",
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


@dataclass(frozen=True)
class Condition:
    name:       str
    dir_prefix: str
    log_prefix: str


CONDITIONS = [
    Condition("final", f"{PREFIX}_final_", f"{PREFIX}_final"),
    Condition("trans", f"{PREFIX}_trans_", f"{PREFIX}_trans"),
]

_USE_COLOR = sys.stdout.isatty()
def _c(code, t): return f"\033[{code}m{t}\033[0m" if _USE_COLOR else t
def red(t):    return _c("91", t)
def yellow(t): return _c("93", t)
def green(t):  return _c("92", t)
def blue(t):   return _c("94", t)
def bold(t):   return _c("1",  t)


def detect_seeds(base_dir: Path) -> list:
    seed_re = re.compile(rf"^{re.escape(PREFIX)}_(final|trans)_(\d+)$")
    seeds = set()
    try:
        with os.scandir(base_dir) as it:
            for entry in it:
                if entry.is_dir():
                    m = seed_re.match(entry.name)
                    if m:
                        seeds.add(int(m.group(2)))
    except OSError:
        pass
    return sorted(seeds)


def _check_cost_dir(cost_path: Path) -> dict:
    missing, empty = [], []
    try:
        sizes = {e.name: e.stat().st_size
                 for e in os.scandir(cost_path) if e.is_file(follow_symlinks=False)}
    except OSError as exc:
        return {"missing": COST_FILES[:], "empty": [], "error": str(exc)}
    for fname in COST_FILES:
        if fname not in sizes:
            missing.append(fname)
        elif sizes[fname] == 0:
            empty.append(fname)
    return {"missing": missing, "empty": empty, "error": None}


def check_seed(seed: int, base_dir: Path, cond: Condition) -> tuple:
    seed_dir = base_dir / f"{cond.dir_prefix}{seed}"
    if not seed_dir.is_dir():
        return seed, {"status": "missing_dir", "cost_dirs": {}}

    cost_re = re.compile(r"^cost_")
    cost_dirs = {}
    try:
        with os.scandir(seed_dir) as it:
            for entry in it:
                if entry.is_dir() and cost_re.match(entry.name):
                    cost_dirs[entry.name] = _check_cost_dir(Path(entry.path))
    except OSError as exc:
        return seed, {"status": "incomplete", "cost_dirs": {}, "error": str(exc)}

    if not cost_dirs:
        return seed, {"status": "incomplete", "cost_dirs": {}}

    any_bad = any(r["missing"] or r["empty"] for r in cost_dirs.values())
    wrong_count = len(cost_dirs) != N_COSTS_EXPECTED
    status = "incomplete" if (any_bad or wrong_count) else "complete"
    return seed, {"status": status, "cost_dirs": cost_dirs}


def check_slurm_logs(base_dir: Path, log_prefix: str) -> dict:
    """Return {filename: (seed, errors, done)} for all matching log files."""
    seed_re = re.compile(r"_(\d+)\.log$")
    results = {}
    for logfile in sorted(base_dir.glob(f"{log_prefix}_*.log")):
        m = seed_re.search(logfile.name)
        seed = int(m.group(1)) if m else None
        try:
            content = logfile.read_text(errors="replace")
        except OSError:
            continue
        errors = [label for pat, label in SLURM_ERROR_PATTERNS if pat.search(content)]
        done = "Done." in content
        results[logfile.name] = (seed, errors, done)
    return results


def _section(title: str, width: int = 64):
    print()
    print(bold("─" * width))
    print(bold(f"  {title}"))
    print(bold("─" * width))


def _print_condition_results(cond, results, log_info, seeds):
    complete     = sorted(s for s, r in results.items() if r["status"] == "complete")
    incomplete   = sorted(s for s, r in results.items() if r["status"] == "incomplete")
    missing_dirs = sorted(s for s, r in results.items() if r["status"] == "missing_dir")
    needs_rerun  = sorted(set(incomplete) | set(missing_dirs))
    total        = len(seeds)

    # Index log info by seed
    seed_log = {}  # seed -> (errors, done)
    for logname, (seed, errors, done) in log_info.items():
        if seed is not None:
            seed_log[seed] = (errors, done)

    _section(f"CONDITION: {cond.name}  ({PREFIX})")

    logs_with_errors = {n: v for n, v in log_info.items() if v[1]}
    if not log_info:
        print(f"  {yellow('Logs: no files found')} matching '{cond.log_prefix}_*.log'")
    elif logs_with_errors:
        print(f"  {red(bold('Log errors:'))}")
        for logname, (seed, errors, done) in sorted(logs_with_errors.items()):
            seed_str = f"seed {seed}" if seed else "unknown"
            print(f"    {red('x')} {bold(logname)}  [{seed_str}]")
            for err in errors:
                print(f"        {red('>')} {err}")
    else:
        print(f"  {green('Logs: no errors')} in {len(log_info)} log file(s).")

    print(f"  {green(bold('Complete  '))}  {len(complete):>3} / {total}"
          f"  (expect {N_COSTS_EXPECTED} cost dirs each)")
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
            cost_dirs = r.get("cost_dirs", {})
            n_ok = sum(1 for v in cost_dirs.values()
                       if not v["missing"] and not v["empty"])
            n_total = len(cost_dirs)
            errors, done = seed_log.get(seed, ([], None))
            if done is True:
                log_tag = green("log:Done")
            elif done is False:
                log_tag = red("log:not Done")
            else:
                log_tag = yellow("log:?")
            count_tag = (green(f"{n_total}/{N_COSTS_EXPECTED} cost dirs")
                         if n_total == N_COSTS_EXPECTED
                         else red(f"{n_total}/{N_COSTS_EXPECTED} cost dirs"))
            print(f"\n    {bold(yellow(f'Seed {seed}'))}  {count_tag}  "
                  f"{n_ok} fully OK  {log_tag}")
            for cost_name, cr in sorted(cost_dirs.items()):
                if cr["missing"] or cr["empty"]:
                    print(f"      {red('x')} {cost_name}/")
                    if cr["missing"]:
                        print(f"          missing: {', '.join(cr['missing'])}")
                    if cr["empty"]:
                        print(f"          empty:   {', '.join(cr['empty'])}")
            if n_total < N_COSTS_EXPECTED:
                print(f"      {yellow(f'Only {n_total} of {N_COSTS_EXPECTED} expected cost dirs present.')}")

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
    args = parser.parse_args()

    base_dir = Path(args.directory).resolve()

    if args.seeds:
        seeds = sorted(int(s) for s in args.seeds.split(","))
    else:
        seeds = detect_seeds(base_dir)
        if not seeds:
            print(red(f"No {PREFIX}_final_<N>/ or {PREFIX}_trans_<N>/ directories found. "
                      "Run from the experiment directory or pass --seeds."))
            sys.exit(1)

    if args.condition == "all":
        target_conditions = [
            c for c in CONDITIONS
            if any((base_dir / f"{c.dir_prefix}{s}").is_dir() for s in seeds)
        ]
        if not target_conditions:
            print(red("No condition directories found for any detected seed."))
            sys.exit(1)
    else:
        target_conditions = [c for c in CONDITIONS if c.name == args.condition]

    print(bold(f"Assay          : {PREFIX}"))
    print(bold(f"Base directory : {base_dir}"))
    print(bold(f"Seeds          : {len(seeds)} detected"))
    print(bold(f"Conditions     : {', '.join(c.name for c in target_conditions)}"))
    print(bold(f"Costs expected : {N_COSTS_EXPECTED} per seed"))

    all_results     = {}
    all_log_info    = {}
    all_needs_rerun = {}

    for cond in target_conditions:
        results = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(check_seed, s, base_dir, cond): s for s in seeds}
            for future in as_completed(futures):
                seed, result = future.result()
                results[seed] = result
        all_results[cond.name]     = results
        all_log_info[cond.name]    = check_slurm_logs(base_dir, cond.log_prefix)
        all_needs_rerun[cond.name] = sorted(
            s for s, r in results.items()
            if r["status"] in ("incomplete", "missing_dir")
        )

    for cond in target_conditions:
        _print_condition_results(cond, all_results[cond.name],
                                 all_log_info[cond.name], seeds)

    if len(target_conditions) > 1:
        _section("GRAND SUMMARY")
        any_failures = False
        for cond in target_conditions:
            rerun = all_needs_rerun[cond.name]
            if rerun:
                any_failures = True
                print(f"  {bold(cond.name)}  ({len(rerun)} seeds):")
                print(f"    {bold(yellow('#SBATCH --array=' + ','.join(str(s) for s in rerun)))}")
            else:
                print(f"  {green(bold(cond.name))}: all complete")
        if not any_failures:
            print()
            print(green(bold("  All conditions complete across all seeds.")))
    print()


if __name__ == "__main__":
    main()
