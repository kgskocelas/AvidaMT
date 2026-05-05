#!/usr/bin/env python3
"""
verify_growth_assay.py

Verify lod_fitness_combo analysis output for all four fitness assay
conditions.  Run from the directory that contains the fitness_end_SEED/,
fitness_trans_SEED/, etc. subdirectories.

All four conditions use track_details=1 and therefore produce an
identical set of output files:

  lod_fitness.dat            ≥100 mc rows
  lod_fit_summary.dat        exactly 1 data row  (primary completion signal)
  multicell_detail.dat       many rows
  unicell_detail.dat         rows if any viable unicell revertants found
  inviable_unicell_detail.dat header-only (declared in code, never written)
  mt_gls_detail_mc_0.dat …
  mt_gls_detail_mc_99.dat    100 files (one per MC rep)
  mt_gls_detail_uni_N_R.dat  variable — one per viable unicell × 100 reps

The four conditions always use the same directory names and log suffix
conventions. Only the experiment-specific log prefix changes per experiment:

 Condition            dir prefix            log name
 ──────────────────── ───────────────────── ──────────────────────────────
 fitness_end          fitness_end_          <LOG_PREFIX>-f_*.log
 fitness_end_no_mut   fitness_end_no_mut_   <LOG_PREFIX>-fnm_*.log
 fitness_trans        fitness_trans_        <LOG_PREFIX>-t_*.log
 fitness_trans_no_mut fitness_trans_no_mut_ <LOG_PREFIX>-tnm_*.log

The experiment log prefix (e.g. "dd") is auto-detected by scanning for
*-f_*.log files in the base directory.

Seeds are auto-detected by scanning for fitness_end_<N>/ directories.
Pass --seeds to override (comma-separated, e.g. --seeds 1011,1069,1088).
"""

import os
import re
import sys
import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ── Condition definitions ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Condition:
    name: str          # human label
    dir_prefix: str    # directory = dir_prefix + str(seed)
    log_suffix: str    # condition-specific log suffix; full prefix = log_prefix + log_suffix

# The dir_prefix and log_suffix are the same for every experiment.
# Only the experiment-level log prefix (e.g. "dd", "ts") changes.
CONDITIONS = [
    Condition("fitness_end",          "fitness_end_",          "-f"),
    Condition("fitness_end_no_mut",   "fitness_end_no_mut_",   "-fnm"),
    Condition("fitness_trans",        "fitness_trans_",        "-t"),
    Condition("fitness_trans_no_mut", "fitness_trans_no_mut_", "-tnm"),
]


def make_conditions(log_prefix: str) -> list:
    """Return CONDITIONS with full log prefixes resolved for this experiment."""
    return [
        Condition(c.name, c.dir_prefix, f"{log_prefix}{c.log_suffix}")
        for c in CONDITIONS
    ]


def detect_log_prefix(base_dir: Path) -> str:
    """Auto-detect the experiment log prefix from *-f_*.log files in base_dir.

    Log files are named <prefix>-f_JOBID_SEED.log, <prefix>-fnm_*.log, etc.
    Returns the prefix string (e.g. 'dd'), or '' if no matching files found.
    """
    prefix_re = re.compile(r"^(.+)-f_.*\.log$")
    try:
        with os.scandir(base_dir) as it:
            for entry in it:
                if entry.is_file():
                    m = prefix_re.match(entry.name)
                    if m:
                        return m.group(1)
    except OSError:
        pass
    return ""


def detect_seeds(base_dir: Path) -> list:
    """Scan base_dir for fitness_end_<N>/ directories and return sorted seed list."""
    seed_re = re.compile(r"^fitness_end_(\d+)$")
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

# Files that must be present AND non-empty.
CORE_FILES = [
    "lod_fitness.dat",
    "lod_fit_summary.dat",
    "multicell_detail.dat",
    "unicell_detail.dat",
]

# Files that must be present but are always empty/header-only by design.
# inviable_unicell_detail.dat: datafile df5 is declared in lod_fitness_combo
# but df5.write() is never called anywhere — the file is created with only a
# header (or 0 bytes) and that is correct, expected behaviour.
CORE_FILES_EXIST_ONLY = [
    "inviable_unicell_detail.dat",
]

SLURM_ERROR_PATTERNS = [
    (re.compile(r"DUE TO TIME LIMIT",     re.I), "time limit"),
    (re.compile(r"oom.kill|out.of.memory",re.I), "OOM killed"),
    (re.compile(r"\bKilled\b",            re.I), "killed (OOM or admin)"),
    (re.compile(r"CANCELLED",             re.I), "cancelled"),
    (re.compile(r"Segmentation fault",    re.I), "segfault"),
    (re.compile(r"terminate called",      re.I), "crash (terminate called)"),
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

# ── File-reading helpers ──────────────────────────────────────────────────────

_MC_DETAIL_RE  = re.compile(r"^mt_gls_detail_mc_(\d+)\.dat$")
_UNI_DETAIL_RE = re.compile(r"^mt_gls_detail_uni_\d+_\d+\.dat$")


def _count_data_lines(path: Path) -> int:
    """Count data lines, skipping blanks, '#' comments, and header lines.

    ealib datafiles write headers without a '#' prefix, so we also skip
    any line whose first token is not numeric.
    """
    try:
        count = 0
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                first = s.split(None, 1)[0]
                if not first.lstrip("-").replace(".", "", 1).isdigit():
                    continue  # header row (e.g. "timepoint num_unicell_revertants …")
                count += 1
        return count
    except OSError:
        return -1


def _count_mc_rows(path: Path) -> int:
    """Count rows where the second whitespace-delimited field is 'mc'."""
    try:
        count = 0
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split(None, 2)
                if len(parts) >= 2 and parts[1] == "mc":
                    count += 1
        return count
    except OSError:
        return -1


def _read_num_viable_unicells(path: Path) -> int:
    """Parse lod_fit_summary.dat and return num_viable_unicells (field index 2).

    Row format: timepoint num_unicell_revertants num_viable_unicells
                num_inviable_unicells update
    Returns -1 on any parse or IO error.
    """
    try:
        with open(path, "r", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split()
                if not parts[0].lstrip("-").replace(".", "", 1).isdigit():
                    continue  # header row
                if len(parts) >= 3:
                    return int(parts[2])
        return -1
    except (OSError, ValueError):
        return -1


# ── Per-seed check ────────────────────────────────────────────────────────────

def check_seed(seed: int, base_dir: Path, cond: Condition) -> tuple:
    """
    Return (seed, result_dict).

    result_dict keys
    ─────────────────
    status              'complete' | 'incomplete' | 'missing_dir'
    missing_files       list[str]  absent core files
    empty_files         list[str]  zero-byte core files
    summary_rows        int|None   None = correct (1 row); int = wrong count
    mc_reps             int|None   None = correct (100); int = actual
    missing_mc_detail   list[int]  rep indices 0–99 that are absent
    mc_detail_found     int        mt_gls_detail_mc_*.dat files present
    uni_detail_count    int        mt_gls_detail_uni_*.dat files found on disk
    uni_detail_expected int|None   num_viable_unicells*100 from lod_fit_summary.dat;
                                   None if summary not yet readable
    detail_data_missing bool       multicell_detail.dat exists but has 0 data rows
    """
    result = {
        "missing_files":      [],
        "empty_files":        [],
        "summary_rows":       None,
        "mc_reps":            None,
        "missing_mc_detail":  [],
        "mc_detail_found":    0,
        "uni_detail_count":   0,
        "uni_detail_expected": None,
        "detail_data_missing": False,
    }

    seed_dir = base_dir / f"{cond.dir_prefix}{seed}"

    if not seed_dir.is_dir():
        result["status"] = "missing_dir"
        return seed, result

    # ── Single scandir pass: sizes + special file sets ────────────────────────
    file_sizes       = {}
    mc_detail_found  = set()
    uni_detail_count = 0

    try:
        with os.scandir(seed_dir) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                name = entry.name
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                file_sizes[name] = size

                m = _MC_DETAIL_RE.match(name)
                if m:
                    mc_detail_found.add(int(m.group(1)))
                elif _UNI_DETAIL_RE.match(name):
                    uni_detail_count += 1
    except PermissionError as exc:
        result["status"] = "incomplete"
        result["missing_files"] = [f"(cannot read directory: {exc})"]
        return seed, result

    result["mc_detail_found"]  = len(mc_detail_found)
    result["uni_detail_count"] = uni_detail_count

    # ── Core file checks ──────────────────────────────────────────────────────
    for fname in CORE_FILES:
        if fname not in file_sizes:
            result["missing_files"].append(fname)
        elif file_sizes[fname] == 0:
            result["empty_files"].append(fname)

    # Existence-only files: must be present but are intentionally empty/header-only.
    for fname in CORE_FILES_EXIST_ONLY:
        if fname not in file_sizes:
            result["missing_files"].append(fname)

    # ── mt_gls_detail_mc files (all 100 expected) ─────────────────────────────
    missing_mc = sorted(set(range(100)) - mc_detail_found)
    result["missing_mc_detail"] = missing_mc

    # ── multicell_detail.dat must have data rows ──────────────────────────────
    mc_detail_name = "multicell_detail.dat"
    if (mc_detail_name not in result["missing_files"]
            and file_sizes.get(mc_detail_name, 0) > 0):
        n = _count_data_lines(seed_dir / mc_detail_name)
        if n == 0:
            result["detail_data_missing"] = True

    # ── Completion signal: lod_fit_summary.dat must have exactly 1 data row ──
    summary_name = "lod_fit_summary.dat"
    if summary_name not in result["missing_files"]:
        if file_sizes.get(summary_name, 0) == 0:
            result["summary_rows"] = 0
        else:
            n = _count_data_lines(seed_dir / summary_name)
            if n != 1:
                result["summary_rows"] = n
            else:
                # Summary is valid — read num_viable_unicells to compute expected
                # uni_detail file count: num_viable_unicells × 100 reps
                nvu = _read_num_viable_unicells(seed_dir / summary_name)
                if nvu >= 0:
                    result["uni_detail_expected"] = nvu * 100

    # ── MC rep count in lod_fitness.dat ──────────────────────────────────────
    fitness_name = "lod_fitness.dat"
    if (fitness_name not in result["missing_files"]
            and file_sizes.get(fitness_name, 0) > 0):
        mc_rows = _count_mc_rows(seed_dir / fitness_name)
        if mc_rows != 100:
            result["mc_reps"] = mc_rows

    # ── Overall status ────────────────────────────────────────────────────────
    # Any deviation from expected output counts as incomplete / needs rerun.
    exp = result["uni_detail_expected"]
    uni_mismatch = (exp is not None and result["uni_detail_count"] != exp)
    failure = (
        result["missing_files"]
        or result["empty_files"]
        or result["summary_rows"] is not None
        or result["detail_data_missing"]
        or result["missing_mc_detail"]
        or result["mc_reps"] is not None
        or uni_mismatch
    )
    result["status"] = "incomplete" if failure else "complete"
    return seed, result


# ── Slurm log check ───────────────────────────────────────────────────────────

def check_slurm_logs(base_dir: Path, prefix: str) -> dict:
    """Return {filename: (seed_or_None, [error_labels])} for error-containing logs."""
    log_issues = {}
    seed_in_name = re.compile(r"_(\d+)\.log$")

    candidates = list(base_dir.glob(f"{prefix}_*.log"))
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


def _mc_detail_range_str(missing: list) -> str:
    """Compress [0,1,2,5,6,99] → '0–2, 5–6, 99'."""
    if not missing:
        return ""
    ranges, start, end = [], missing[0], missing[0]
    for v in missing[1:]:
        if v == end + 1:
            end = v
        else:
            ranges.append(str(start) if start == end else f"{start}–{end}")
            start = end = v
    ranges.append(str(start) if start == end else f"{start}–{end}")
    return ", ".join(ranges)


def _seed_grid(seeds: list, cols: int = 10):
    per_line = []
    for i, s in enumerate(seeds):
        per_line.append(f"{s:>5}")
        if (i + 1) % cols == 0:
            print("  " + "  ".join(per_line))
            per_line = []
    if per_line:
        print("  " + "  ".join(per_line))


def _print_uni_detail_line(r: dict, indent: int = 6):
    """Print the unicell detail file count as 'actual / expected' with status icon."""
    pad = " " * indent
    actual   = r["uni_detail_count"]
    expected = r["uni_detail_expected"]

    if expected is None:
        # Summary not available yet — can't compute expected
        print(f"{pad}{blue('ℹ Unicell detail files:')}  {actual}  {dim('(expected unknown — summary unreadable)')}")
    elif actual == expected:
        print(f"{pad}{blue('ℹ Unicell detail files:')}  {green(f'{actual} / {expected}')}  {dim('✓')}")
    else:
        missing = expected - actual
        print(f"{pad}{yellow('⚠ Unicell detail files:')}  "
              f"{yellow(f'{actual} / {expected}')}  "
              f"{red(f'({missing} missing)')}")


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
            found = list(base_dir.glob(f"{cond.log_suffix}_*.log"))
            if found:
                print(f"  {green('Logs: no errors')} in {len(found)} log file(s).")
            else:
                print(f"  {yellow('Logs: no files found')} matching '{cond.log_suffix}_*.log'")
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
                print(f"      {red('✗ Empty files:')}    {', '.join(r['empty_files'])}")

            sr = r["summary_rows"]
            if sr is not None:
                if sr == 0:
                    print(f"      {red('✗ lod_fit_summary.dat:')}  0 data rows — job did not finish")
                elif sr == -1:
                    print(f"      {red('✗ lod_fit_summary.dat:')}  unreadable")
                else:
                    print(f"      {red('✗ lod_fit_summary.dat:')}  {sr} rows (expected 1)")

            if r["detail_data_missing"]:
                print(f"      {red('✗ multicell_detail.dat:')}  exists but has 0 data rows")

            mc = r["mc_reps"]
            if mc is not None:
                bar_filled = int(mc / 100 * 20)
                bar = "█" * bar_filled + "░" * (20 - bar_filled)
                print(f"      {red('✗ MC reps completed:')}  {mc:>3}/100  [{bar}]")

            mcd = r["missing_mc_detail"]
            found = r["mc_detail_found"]
            if mcd:
                if len(mcd) <= 15:
                    print(f"      {red('✗ Missing mt_gls_detail_mc files:')}  "
                          f"reps {_mc_detail_range_str(mcd)}")
                else:
                    print(f"      {red('✗ Missing mt_gls_detail_mc files:')}  "
                          f"{len(mcd)}/100 absent  "
                          f"(first missing: rep {mcd[0]};  {found} present)")

            _print_uni_detail_line(r, indent=6)

    # ── Re-run array ──────────────────────────────────────────────────────────
    print()
    if not needs_rerun:
        print(f"  {green(bold(f'✓ All {total} seeds complete.'))}")
    else:
        array_str = ','.join(str(s) for s in needs_rerun)
        print(f"  {red(bold(f'{len(needs_rerun)} seed(s) need rerun:'))}")
        print(f"  {bold(yellow(f'sbatch --array={array_str}'))}")


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
        help="Comma-separated seed list to check (default: auto-detect from fitness_end_N/ dirs)",
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
    log_prefix = detect_log_prefix(base_dir)
    all_conditions  = make_conditions(log_prefix)
    target_conditions = all_conditions if args.condition == "all" \
                        else [c for c in all_conditions if c.name == args.condition]

    if args.seeds:
        seeds = sorted(int(s) for s in args.seeds.split(","))
    else:
        seeds = detect_seeds(base_dir)
        if not seeds:
            print(red("No fitness_end_<N>/ directories found. "
                      "Run from the experiment directory or pass --seeds."))
            sys.exit(1)

    print(bold(f"Base directory : {base_dir}"))
    print(bold(f"Seeds          : {len(seeds)} detected"))
    print(bold(f"Log prefix     : '{log_prefix}'  (e.g. {log_prefix}-f_*.log)")
          if log_prefix else bold("Log prefix     : (not detected — log scanning skipped)"))
    print(bold(f"Conditions     : {', '.join(c.name for c in target_conditions)}"))
    print(bold(f"Workers        : {args.workers if args.workers is not None else 'unlimited'}"))

    # ── Collect all results first ─────────────────────────────────────────────
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
            check_slurm_logs(base_dir, cond.log_suffix)
            if not args.no_logs else {}
        )
        all_needs_rerun[cond.name] = sorted(
            s for s, r in results.items()
            if r["status"] in ("incomplete", "missing_dir")
        )

    # ── Seed-set consistency check (first thing printed) ─────────────────────
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
            print(f"  {green(bold('✓'))} All {len(target_conditions)} conditions were run "
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

    # ── Remove failed seed directories ───────────────────────────────────────
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

        # ── Write missing_seeds.txt ───────────────────────────────────────────
        missing_seeds_path = base_dir / "missing_seeds.txt"
        with open(missing_seeds_path, "w") as fh:
            for cond in target_conditions:
                rerun = all_needs_rerun[cond.name]
                fh.write(f"# {cond.name}\n")
                if rerun:
                    fh.write(f"sbatch --array={','.join(str(s) for s in rerun)}\n")
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
                print(f"    {bold(yellow(f'sbatch --array={array_str}'))}")
            else:
                print(f"  {green(bold(cond.name))}: all complete")
        if not any_failures:
            print()
            print(green(bold("  ✓ All conditions complete across all seeds.")))

    print()


if __name__ == "__main__":
    main()
