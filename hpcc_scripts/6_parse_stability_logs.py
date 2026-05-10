#!/usr/bin/env python3
"""
Parse all final_*.log and trans_*.log files from the stability (entrenchment)
assay array jobs and summarize which costs each seed completed.

Usage:
    python3 parse_stability_logs.py [LOG_DIR]

    LOG_DIR defaults to the current directory.
"""

import re
import sys
from pathlib import Path
from collections import defaultdict

ALL_COSTS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

def parse_log(path: Path) -> dict:
    seed = None
    costs_started = []
    costs_completed = []
    cancelled = False
    finished = False  # reached the final 'date' call

    # Detect timepoint and seed from filename: final_JOBID_SEED.log or trans_JOBID_SEED.log
    timepoint = 'unknown'
    m = re.search(r'(final|trans)_\d+_(\d+)\.log', path.name)
    if m:
        timepoint = 'final' if m.group(1) == 'final' else 'transition'
        seed = int(m.group(2))

    current_cost = None
    with open(path, 'r', errors='replace') as f:
        for line in f:
            line = line.strip()

            # Seed can also appear in the log body
            if seed is None:
                m = re.search(r'Seed:\s*(\d+)', line)
                if m:
                    seed = int(m.group(1))

            # Cost started
            m = re.match(r'Cost:\s*(\d+)', line)
            if m:
                current_cost = int(m.group(1))
                costs_started.append(current_cost)

            # Cost's loading step completed
            if line.endswith('done.') and 'loading' in line and current_cost is not None:
                costs_completed.append(current_cost)

            # Job cancelled by SLURM time limit
            if 'CANCELLED' in line and 'TIME LIMIT' in line:
                cancelled = True

            # Final date line (last line of a successful run)
            # The script ends with `date`, which produces a line like "Fri May  8 ..."
            # We detect a completed run by presence of a second date line after the header date
        
    # A run is "finished" if it completed all costs AND wasn't cancelled
    finished = (not cancelled) and (set(ALL_COSTS).issubset(set(costs_completed)))

    last_completed = costs_completed[-1] if costs_completed else None
    last_started = costs_started[-1] if costs_started else None

    # Did the last started cost also complete?
    last_cost_complete = (last_started is not None and
                          last_started in costs_completed)

    return {
        'seed': seed,
        'timepoint': timepoint,
        'path': path.name,
        'costs_started': costs_started,
        'costs_completed': costs_completed,
        'n_completed': len(costs_completed),
        'last_completed': last_completed,
        'last_started': last_started,
        'last_cost_complete': last_cost_complete,
        'cancelled': cancelled,
        'fully_done': finished,
    }


def main():
    log_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
    log_files = sorted(log_dir.glob('final_*.log')) + sorted(log_dir.glob('trans_*.log'))

    if not log_files:
        print(f"No final_*.log or trans_*.log files found in {log_dir}")
        sys.exit(1)

    all_results = [parse_log(p) for p in log_files]

    # Group by timepoint and sort by seed within each group
    for timepoint_label in ('final', 'transition'):
        results = [r for r in all_results if r['timepoint'] == timepoint_label]
        if not results:
            continue
        results.sort(key=lambda r: r['seed'] if r['seed'] is not None else -1)

        print_section(results, timepoint_label)


def print_section(results, timepoint_label):
    fully_done = [r for r in results if r['fully_done']]
    cancelled  = [r for r in results if r['cancelled']]
    incomplete = [r for r in results if not r['fully_done']]

    label = timepoint_label.upper()
    print()
    print(f"{'='*60}")
    print(f"  {label} TIMEPOINT — {len(results)} jobs")
    print(f"{'='*60}")
    print(f"  Fully completed (all 12 costs): {len(fully_done)}")
    print(f"  Cancelled by time limit:        {len(cancelled)}")
    print(f"  Incomplete (any reason):        {len(incomplete)}")
    print()

    # ── Per-seed detail ───────────────────────────────────────────────────────
    print(f"{'SEED':<8} {'COMPLETED':<12} {'LAST COST DONE':<16} {'CANCELLED':<10} STATUS")
    print(f"{'-'*8} {'-'*12} {'-'*16} {'-'*10} {'-'*20}")
    for r in results:
        seed_str    = str(r['seed']) if r['seed'] is not None else '???'
        n_done      = f"{r['n_completed']}/12"
        last_done   = str(r['last_completed']) if r['last_completed'] else 'none'
        cancelled_s = 'YES' if r['cancelled'] else 'no'
        if r['fully_done']:
            status = 'DONE'
        elif r['cancelled']:
            status = f"TIMED OUT (stopped at cost {r['last_started']})"
        else:
            status = 'INCOMPLETE / ERROR'
        print(f"{seed_str:<8} {n_done:<12} {last_done:<16} {cancelled_s:<10} {status}")

    # ── Seeds that need to be re-run ─────────────────────────────────────────
    if incomplete:
        print()
        print(f"Seeds needing re-run ({timepoint_label}):")
        seeds_to_rerun = [str(r['seed']) for r in incomplete if r['seed'] is not None]
        print(','.join(seeds_to_rerun))

    # ── Cost histogram ────────────────────────────────────────────────────────
    print()
    print("Cost completion histogram (how many seeds finished each cost level):")
    print(f"  {'COST':<8} {'SEEDS COMPLETED'}")
    cost_counts = defaultdict(int)
    for r in results:
        for c in r['costs_completed']:
            cost_counts[c] += 1
    for c in ALL_COSTS:
        bar = '#' * cost_counts[c]
        print(f"  {c:<8} {cost_counts[c]:>3}  {bar}")


if __name__ == '__main__':
    main()
