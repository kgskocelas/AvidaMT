#!/usr/bin/env python3
"""
1_summarize_run_data.py

Post-run analysis for AvidaMT experiments. Run from inside a phase directory
(uni or multi) after jobs complete.

Reads:
  - dat files in seed subdirectories   → MC status, final update
  - *.log files                         → failure type (TIMEOUT, OOM, ERROR)
  - resource_usage_summary.txt          → elapsed time, peak memory per seed

Writes:
  - summary_<dat>.csv
  - next-array.txt              (MC seeds ready/nearly ready for LOD)
  - next-array.txt        (failed non-MC seeds)

Prints a full action plan with copy-paste #SBATCH lines.
"""

# ── User configuration ────────────────────────────────────────────────────────
DAT_FILE_NAME        = "mt_gls.dat"
TARGET_FINAL_UPDATE  = 999900
MC_THRESHOLD         = 2.0
MAX_WORKERS          = None  # None = all available CPU cores

# Safety multipliers applied on top of observed / extrapolated values.
# LOD multipliers are based on code analysis: record_lod=1 stores a full copy
# of every subpopulation founder in RAM (continuous growth) and writes large
# XML lineage files per epoch — roughly 1.2x more time, 2-5x more memory.
TIME_RERUN_MULT    = 1.5   # buffer for non-LOD reruns
MEMORY_RERUN_MULT  = 1.5   # buffer for non-LOD reruns
LOD_TIME_MULT      = 1.8   # ~1.2x LOD overhead × ~1.5x safety
LOD_MEMORY_MULT    = 3.0   # founder copies accumulate; 3x observed peak is safe
# ─────────────────────────────────────────────────────────────────────────────

import csv
import math
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ENDS_IN_4_DIGITS = re.compile(r"\d{4}$")
W = 78  # output width


# ══════════════════════════════════════════════════════════════════════════════
# Data readers
# ══════════════════════════════════════════════════════════════════════════════

def _read_tail_bytes(f, chunk=4096):
    f.seek(0, 2)
    size = f.tell()
    if size == 0:
        return b""
    buf, pos = b"", size
    while pos > 0:
        read_size = min(chunk, pos)
        pos -= read_size
        f.seek(pos)
        buf = f.read(read_size) + buf
        stripped = buf.rstrip(b"\r\n")
        if b"\n" in stripped:
            last = stripped.rsplit(b"\n", 1)[-1].strip()
            if last:
                return last
    return buf.strip()


def _read_header(path):
    with path.open("rb") as f:
        for raw in f:
            line = raw.strip()
            if line:
                return line.decode().split()
    return []


def _process_folder(args):
    folder_path, dat_filename, target_update, mc_threshold = args
    name = folder_path.name
    seed = int(name[-4:])
    dat_path = folder_path / dat_filename
    if not dat_path.exists():
        return {"seed": seed, "folder": name, "status": "skip",
                "reason": f"missing {dat_filename}"}
    try:
        header = _read_header(dat_path)
        if not header:
            return {"seed": seed, "folder": name, "status": "skip", "reason": "empty file"}
        try:
            ui = header.index("update")
            mi = header.index("mean_multicell_size")
        except ValueError as e:
            return {"seed": seed, "folder": name, "status": "skip",
                    "reason": f"missing column: {e}"}
        with dat_path.open("rb") as f:
            last = _read_tail_bytes(f)
        if not last:
            return {"seed": seed, "folder": name, "status": "skip", "reason": "no data rows"}
        row = last.decode().split()
        final_update = int(float(row[ui]))
        mmc = float(row[mi])
        return {
            "seed": seed, "folder": name, "status": "ok",
            "final_update": final_update,
            "mean_multicell_size": mmc,
            "failed": final_update != target_update,
            "mc": mmc >= mc_threshold,
        }
    except Exception as e:
        return {"seed": seed, "folder": name, "status": "skip", "reason": str(e)}


def read_dat_files(base_dir):
    candidates = [
        Path(e.path) for e in os.scandir(base_dir)
        if e.is_dir() and ENDS_IN_4_DIGITS.search(e.name)
    ]
    if not candidates:
        print("No directories ending in 4 digits found.", file=sys.stderr)
        sys.exit(1)
    print(f"Reading {len(candidates)} seed directories...")
    work = [(p, DAT_FILE_NAME, TARGET_FINAL_UPDATE, MC_THRESHOLD)
            for p in sorted(candidates)]
    results, skipped = {}, []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_process_folder, w): w for w in work}
        for fut in as_completed(futures):
            r = fut.result()
            if r["status"] == "ok":
                results[r["seed"]] = r
            else:
                skipped.append((r["folder"], r.get("reason", "?")))
    if skipped:
        print(f"Skipped {len(skipped)} directories (no usable dat file):")
        for folder, reason in sorted(skipped):
            print(f"  {folder}: {reason}")
    return results


def read_log_failures(base_dir):
    """Return dict[seed -> reason] for seeds with detectable failures in .log files."""
    failures = {}
    for logfile in sorted(Path(base_dir).glob("*.log")):
        m = re.search(r"_(\d+)\.log$", logfile.name)
        if not m:
            continue
        seed = int(m.group(1))
        text = logfile.read_text(errors="replace")
        if "DUE TO TIME LIMIT" in text:
            failures[seed] = "TIMEOUT"
        elif ("DUE TO MEM" in text or "OUT_OF_MEMORY" in text
              or "oom-kill" in text.lower()):
            failures[seed] = "OOM"
        elif "CANCELLED" in text:
            failures[seed] = "CANCELLED"
        elif re.search(r"\berror\b", text, re.IGNORECASE) and "DUE TO" not in text:
            failures[seed] = "ERROR"
    return failures


def read_resource_summary(base_dir):
    """Parse resource_usage_summary.txt → dict[seed -> {elapsed_sec, peak_mem_mb}]."""
    path = Path(base_dir) / "resource_usage_summary.txt"
    if not path.exists():
        return {}
    data = {}
    with path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                seed = int(row["seed"])
                data[seed] = {
                    "elapsed_sec": int(row["elapsed_sec"]),
                    "peak_mem_mb": float(row["peak_mem_mb"]),
                }
            except (KeyError, ValueError):
                continue
    return data


# ══════════════════════════════════════════════════════════════════════════════
# Formatting helpers
# ══════════════════════════════════════════════════════════════════════════════

def fmt_elapsed(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h}h{m:02d}m{s:02d}s"


def sbatch_time(seconds):
    hours = max(1, math.ceil(seconds / 3600))
    return f"{hours}:00:00"


def sbatch_mem(mb):
    return f"{math.ceil(mb / 1024)}G"


def write_array_file(path, lines):
    """Write lines to path, overwriting if it exists. Returns (verb, still_missing)."""
    existed = path.exists()
    path.write_text("\n".join(lines) + "\n")
    return ("Updated" if existed else "Wrote"), any("???" in l for l in lines)


def extrapolate_time(elapsed_sec, final_update):
    """Estimate total run time assuming linear scaling to TARGET_FINAL_UPDATE."""
    if final_update <= 0:
        return None
    return elapsed_sec * TARGET_FINAL_UPDATE / final_update


def array_str(seeds):
    return "#SBATCH --array=" + ",".join(str(s) for s in sorted(seeds))



# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    base_dir = Path.cwd()

    dat        = read_dat_files(base_dir)
    log_fail   = read_log_failures(base_dir)
    resources  = read_resource_summary(base_dir)
    has_res    = bool(resources)

    # ── Write CSV ─────────────────────────────────────────────────────────────
    csv_name = f"summary_{Path(DAT_FILE_NAME).stem}.csv"
    rows_sorted = sorted(dat.values(), key=lambda r: (r["final_update"], r["seed"]))
    with (base_dir / csv_name).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "folder", "final_update", "mean_multicell_size", "failed", "MC"])
        for r in rows_sorted:
            w.writerow([r["seed"], r["folder"], r["final_update"],
                        r["mean_multicell_size"],
                        "T" if r["failed"] else "F",
                        "T" if r["mc"] else "F"])
    print(f"Wrote {len(rows_sorted)} rows → {csv_name}")

    # ── Classify seeds ────────────────────────────────────────────────────────
    completed_mc    = []  # MC=T, failed=F — ready for LOD
    mc_resource     = []  # MC=T, failed=T, TIMEOUT/OOM/CANCELLED — LOD needed, check resources
    mc_crashed      = []  # MC=T, failed=T, ERROR or unknown — debug first
    rerun_timeout   = []  # MC=F, failed=T, TIMEOUT or CANCELLED
    rerun_oom       = []  # MC=F, failed=T, OOM
    crashed         = []  # MC=F, failed=T, ERROR
    failed_unknown  = []  # MC=F, failed=T, no log failure found

    for seed, r in sorted(dat.items()):
        reason = log_fail.get(seed)
        if r["mc"] and not r["failed"]:
            completed_mc.append(seed)
        elif r["mc"] and r["failed"]:
            if reason in ("TIMEOUT", "OOM", "CANCELLED"):
                mc_resource.append(seed)
            else:
                mc_crashed.append(seed)
        elif not r["mc"] and not r["failed"]:
            pass  # finished, no MC — nothing to do
        else:  # not mc, failed
            if reason in ("TIMEOUT", "CANCELLED"):
                rerun_timeout.append(seed)
            elif reason == "OOM":
                rerun_oom.append(seed)
            elif reason == "ERROR":
                crashed.append(seed)
            else:
                failed_unknown.append(seed)

    lod_seeds     = sorted(set(completed_mc + mc_resource))  # all MC seeds excluding crashed
    rerun_seeds   = sorted(set(rerun_timeout + rerun_oom + failed_unknown))
    debug_seeds   = sorted(set(crashed + mc_crashed))


    # ══════════════════════════════════════════════════════════════════════════
    # Action plan
    # ══════════════════════════════════════════════════════════════════════════

    print()
    print("=" * W)
    print("  ANALYSIS COMPLETE — ACTION PLAN")
    print("=" * W)

    # Summary counts
    completed_non_mc = [s for s, r in dat.items() if not r["mc"] and not r["failed"]]
    print(f"\n  Seeds processed:  {len(dat)}")
    print(f"    Completed (MC=F):                  {len(completed_non_mc)}")
    print(f"    Completed (MC=T, ready for LOD):   {len(completed_mc)}")
    if mc_resource:
        print(f"    MC=T, ran out of resources:        {len(mc_resource)}  ← need LOD, check resources")
    if mc_crashed:
        print(f"    MC=T, crashed:                     {len(mc_crashed)}  ← debug before LOD")
    if rerun_timeout:
        print(f"    MC=F, timed out:                   {len(rerun_timeout)}  ← rerun with more time")
    if rerun_oom:
        print(f"    MC=F, out of memory:               {len(rerun_oom)}  ← rerun with more memory")
    if crashed:
        print(f"    MC=F, crashed:                     {len(crashed)}  ← debug")
    if failed_unknown:
        print(f"    MC=F, failed (cause unknown):      {len(failed_unknown)}  ← investigate")
    if not has_res:
        print()
        print("  NOTE: resource_usage_summary.txt not found. Time/memory recommendations")
        print("  will be rough. Run flock in your sbatch to enable resource tracking.")

    # ─────────────────────────────────────────────────────────────────────────
    # ACTION A: Debug crashes  (highest priority — fix before anything else)
    # ─────────────────────────────────────────────────────────────────────────
    if debug_seeds:
        print()
        print("=" * W)
        print("  ACTION A — Debug seeds that crashed")
        print("=" * W)
        print()
        print("  These seeds failed with an ERROR — not a SLURM resource limit.")
        print("  This likely means a bug in the code or a bad configuration.")
        print("  Do NOT rerun them for data collection purposes until the crash is diagnosed.")
        print()
        for s in debug_seeds:
            r = dat[s]
            res = resources.get(s)
            pct = r["final_update"] / TARGET_FINAL_UPDATE * 100
            mc_tag = " [MC=T — LOD blocked]" if r["mc"] else ""
            elapsed = f", elapsed {fmt_elapsed(res['elapsed_sec'])}" if res else ""
            print(f"  Seed {s}{mc_tag}: crashed at update {r['final_update']:,} ({pct:.1f}%){elapsed}")

        print()
        print("  To diagnose:")
        print("  1. Add '#SBATCH -e slurm_%j.err' to your sbatch to get a separate")
        print("     stderr file. Resubmit one failing seed and read the .err log.")
        print("  2. If that doesn't tell you enough, recompile in debug mode with AddressSanitizer.")
        print("     Copy the resulting executable into config/ and resubmit.")
        print("     The .err log will include a full call stack showing where it crashed.")
        print("     See INSTALL.md for the full debugging build instructions and tips.")
        if rerun_seeds:
            print()
            print("  NOTE: There are also non-MC seeds to rerun (see below), but fix crashes first.")
        if lod_seeds:
            print()
            print("  NOTE: There are MC seeds ready for LOD, but fix crashes first.")

    # ─────────────────────────────────────────────────────────────────────────
    # ACTION B: Rerun failed non-MC seeds  (only if no crashes outstanding)
    # ─────────────────────────────────────────────────────────────────────────
    if rerun_seeds and not debug_seeds:
        print()
        print("=" * W)
        print("  ACTION B — Rerun failed non-MC seeds")
        print("=" * W)
        print()
        print("  These seeds did not evolve multicellularity and were cut short by SLURM.")
        print("  Rerun with record_lod=0 (or absent) in config/ramp.cfg.")

        print()
        print(f"  {'Seed':<8} {'Reason':<12} {'Final update':<16} {'Progress':<10} {'Elapsed':<14} {'Peak mem'}")
        print("  " + "-" * 68)
        for s in rerun_seeds:
            r = dat[s]
            reason = log_fail.get(s, "unknown")
            res = resources.get(s)
            pct = r["final_update"] / TARGET_FINAL_UPDATE * 100
            elapsed = fmt_elapsed(res["elapsed_sec"]) if res else "N/A"
            mem = f"{res['peak_mem_mb']:.0f} MB" if res else "N/A"
            if reason == "OOM":
                mem = "OOM (unknown)"
            print(f"  {s:<8} {reason:<12} {r['final_update']:<16,} {pct:<10.1f}% {elapsed:<14} {mem}")

        cancelled = [s for s in rerun_seeds if log_fail.get(s) == "CANCELLED"]
        if cancelled:
            print(f"\n  NOTE: Seed(s) {cancelled} were CANCELLED (not a resource limit).")
            print("  Verify you actually want to rerun these before including them.")

        if failed_unknown:
            print(f"\n  NOTE: Seed(s) {sorted(failed_unknown)} failed but no failure keyword was found")
            print("  in their logs (logs may have been deleted or the failure was silent).")
            print("  Included in the rerun array. If they keep failing, check for crashes")
            print("  by adding '#SBATCH -e slurm_%j.err' to separate stderr output.")

        # ── Compute resource recommendations and write file ───────────────
        file_lines = [array_str(rerun_seeds), ""]
        if has_res:
            time_ests = []
            for s in rerun_timeout:
                r = dat[s]
                res = resources.get(s)
                if res and r["final_update"] > 0:
                    est = extrapolate_time(res["elapsed_sec"], r["final_update"])
                    if est:
                        time_ests.append((s, est))

            completed_times = [
                resources[s]["elapsed_sec"]
                for s in dat if not dat[s]["failed"] and s in resources
            ]
            non_oom_peaks = [
                resources[s]["peak_mem_mb"]
                for s in rerun_timeout if s in resources
            ]
            completed_peaks = [
                resources[s]["peak_mem_mb"]
                for s in dat if not dat[s]["failed"] and s in resources
            ]
            all_peaks = non_oom_peaks + completed_peaks

            if time_ests:
                best_t = max(time_ests, key=lambda x: x[1])
                rec_t_sec = best_t[1] * TIME_RERUN_MULT
                rec_t_str = sbatch_time(rec_t_sec)
                t_comment = [
                    f"# Time:   worst extrapolated: {fmt_elapsed(best_t[1])} (seed {best_t[0]})",
                    f"#         × {TIME_RERUN_MULT:.1f}x buffer = {fmt_elapsed(rec_t_sec)}",
                ]
            elif completed_times:
                max_t = max(completed_times)
                rec_t_sec = max_t * TIME_RERUN_MULT
                rec_t_str = sbatch_time(rec_t_sec)
                t_comment = [
                    f"# Time:   no timeout seeds; used max completed run: {fmt_elapsed(max_t)}",
                    f"#         × {TIME_RERUN_MULT:.1f}x buffer = {fmt_elapsed(rec_t_sec)}",
                ]
            else:
                rec_t_str = "???"
                t_comment = [
                    "# Time:   resource_usage_summary.txt has no elapsed-time data for these seeds.",
                    f"#         Open it, find max elapsed_sec, then set --time = ceil(max / 3600 × {TIME_RERUN_MULT:.1f}):00:00",
                ]

            if all_peaks:
                max_p = max(all_peaks)
                rec_m_mb = max_p * MEMORY_RERUN_MULT
                rec_m_str = sbatch_mem(rec_m_mb)
                src = "timed-out seeds" if non_oom_peaks else "completed seeds"
                m_comment = [
                    f"# Memory: max observed peak ({src}): {max_p:.0f} MB",
                    f"#         × {MEMORY_RERUN_MULT:.1f}x buffer = {rec_m_mb:.0f} MB",
                ]
                if rerun_oom:
                    m_comment += [
                        "#",
                        f"# NOTE: OOM seeds {sorted(rerun_oom)} have no recorded peak.",
                        "# This estimate may be too low. If they OOM again, double --mem for those seeds.",
                    ]
            else:
                rec_m_str = "???"
                m_comment = [
                    "# Memory: resource_usage_summary.txt has no peak-memory data for these seeds.",
                    f"#         Open it, find max peak_mem_mb, then set --mem = ceil(max / 1024 × {MEMORY_RERUN_MULT:.1f})G",
                ]

            file_lines += [
                f"#SBATCH --time={rec_t_str}",
                f"#SBATCH --mem={rec_m_str}",
                "",
                f"# Resource recommendations (multipliers: {TIME_RERUN_MULT:.1f}x time, {MEMORY_RERUN_MULT:.1f}x memory)",
            ] + t_comment + m_comment
        else:
            file_lines += [
                "#SBATCH --time=???",
                "#SBATCH --mem=???",
                "",
                "# resource_usage_summary.txt not found — cannot recommend --time or --mem.",
                "# Find max elapsed time and max peak memory via sacct or job logs, then set:",
                f"#   --time = ceil(max_elapsed_hours × {TIME_RERUN_MULT:.1f}):00:00",
                f"#   --mem  = ceil(max_peak_MB / 1024 × {MEMORY_RERUN_MULT:.1f})G",
            ]

        verb, missing = write_array_file(base_dir / "next-array.txt", file_lines)
        print()
        print(f"  {verb} next-array.txt ({len(rerun_seeds)} seeds + resource recommendations).")
        if missing:
            print("  WARNING: --time or --mem still ??? — fill those in before submitting.")

        if lod_seeds:
            print()
            print("  NOTE: There are MC seeds ready for LOD. Run those after reruns complete.")

    # ─────────────────────────────────────────────────────────────────────────
    # ACTION C: LOD reruns  (only if no crashes or reruns outstanding)
    # ─────────────────────────────────────────────────────────────────────────
    if (lod_seeds or mc_crashed) and not debug_seeds and not rerun_seeds:
        print()
        print("=" * W)
        print("  ACTION C — Run LOD reruns for MC seeds")
        print("=" * W)
        print()
        print("  Seeds that evolved multicellularity need to be rerun with record_lod=1.")
        print("  LOD runs re-execute from scratch and write large XML lineage files,")
        print("  using more time and memory than a normal run.")

        if completed_mc:
            print(f"\n  Ready now (MC=T, completed): {len(completed_mc)} seeds — listed in next-array.txt")

        if mc_resource:
            print(f"\n  Need resource check before LOD (MC=T, failed by SLURM):")
            print(f"  These seeds evolved MC but were cut off by a resource limit.")
            print(f"  They do NOT need to be base-rerun — the LOD run will cover them.")
            print(f"  Make sure the LOD resource allocation is enough for them to finish.\n")
            print(f"  {'Seed':<8} {'Reason':<12} {'Final update':<16} {'Progress':<10} {'Elapsed':<14} {'Peak mem'}")
            print("  " + "-" * 68)
            for s in sorted(mc_resource):
                r = dat[s]
                reason = log_fail.get(s, "unknown")
                res = resources.get(s)
                pct = r["final_update"] / TARGET_FINAL_UPDATE * 100
                elapsed = fmt_elapsed(res["elapsed_sec"]) if res else "N/A"
                mem = f"{res['peak_mem_mb']:.0f} MB" if res else "N/A"
                if reason == "OOM":
                    mem = "OOM (unknown)"
                print(f"  {s:<8} {reason:<12} {r['final_update']:<16,} {pct:<10.1f}% {elapsed:<14} {mem}")

        if mc_crashed:
            print(f"\n  CRASHED — do not include in LOD array until debugged:")
            print(f"  {sorted(mc_crashed)}  (see Action A)")

        # ── Compute resource recommendations and write file ───────────────
        file_lines = [array_str(lod_seeds), ""]
        if has_res:
            time_data = []
            for s in lod_seeds:
                r = dat[s]
                res = resources.get(s)
                if not res:
                    continue
                if not r["failed"]:
                    time_data.append((s, res["elapsed_sec"], "observed"))
                elif r["final_update"] > 0:
                    est = extrapolate_time(res["elapsed_sec"], r["final_update"])
                    if est:
                        rough = r["final_update"] / TARGET_FINAL_UPDATE < 0.25
                        label = "extrapolated (rough — <25% done)" if rough else "extrapolated"
                        time_data.append((s, est, label))

            mem_data = []
            for s in lod_seeds:
                r = dat[s]
                res = resources.get(s)
                if res and not r["failed"] and res["peak_mem_mb"] > 0:
                    mem_data.append((s, res["peak_mem_mb"]))
                elif res and log_fail.get(s) == "TIMEOUT" and res["peak_mem_mb"] > 0:
                    mem_data.append((s, res["peak_mem_mb"]))

            if time_data:
                best_t = max(time_data, key=lambda x: x[1])
                rec_t_sec = best_t[1] * LOD_TIME_MULT
                rec_t_str = sbatch_time(rec_t_sec)
                t_comment = [
                    f"# Time:   worst case {best_t[2]}: {fmt_elapsed(best_t[1])} (seed {best_t[0]})",
                    f"#         × {LOD_TIME_MULT:.1f} LOD factor = {fmt_elapsed(rec_t_sec)}",
                ]
            else:
                rec_t_str = "???"
                t_comment = [
                    "# Time:   resource_usage_summary.txt has no elapsed-time data for these seeds.",
                    f"#         Open it, find max elapsed_sec, then set --time = ceil(max / 3600 × {LOD_TIME_MULT:.1f}):00:00",
                ]

            if mem_data:
                best_m = max(mem_data, key=lambda x: x[1])
                rec_m_mb = best_m[1] * LOD_MEMORY_MULT
                rec_m_str = sbatch_mem(rec_m_mb)
                m_comment = [
                    f"# Memory: max observed peak: {best_m[1]:.0f} MB (seed {best_m[0]})",
                    f"#         × {LOD_MEMORY_MULT:.0f}x LOD factor = {rec_m_mb:.0f} MB",
                ]
                mc_oom_seeds = [s for s in mc_resource if log_fail.get(s) == "OOM"]
                if mc_oom_seeds:
                    m_comment += [
                        "#",
                        f"# WARNING: Seed(s) {mc_oom_seeds} ran out of memory on the base run.",
                        "# Their LOD memory requirement may be higher than this estimate.",
                        "# If they fail again, consider doubling --mem for those seeds.",
                    ]
            else:
                rec_m_str = "???"
                m_comment = [
                    "# Memory: resource_usage_summary.txt has no peak-memory data for these seeds.",
                    f"#         Open it, find max peak_mem_mb, then set --mem = ceil(max / 1024 × {LOD_MEMORY_MULT:.0f})G",
                ]

            file_lines += [
                f"#SBATCH --time={rec_t_str}",
                f"#SBATCH --mem={rec_m_str}",
                "",
                "# Set record_lod=1 in config/ramp.cfg before submitting.",
                f"# Resource recommendations (multipliers: {LOD_TIME_MULT:.1f}x time, {LOD_MEMORY_MULT:.0f}x memory)",
            ] + t_comment + m_comment
        else:
            file_lines += [
                "#SBATCH --time=???",
                "#SBATCH --mem=???",
                "",
                "# Set record_lod=1 in config/ramp.cfg before submitting.",
                "# resource_usage_summary.txt not found — cannot recommend --time or --mem.",
                "# Find max elapsed time and max peak memory via sacct or job logs, then set:",
                f"#   --time = ceil(max_elapsed_hours × {LOD_TIME_MULT:.1f}):00:00",
                f"#   --mem  = ceil(max_peak_MB / 1024 × {LOD_MEMORY_MULT:.0f})G",
            ]

        verb, missing = write_array_file(base_dir / "next-array.txt", file_lines)
        print()
        print(f"  {verb} next-array.txt ({len(lod_seeds)} seeds + resource recommendations).")
        if missing:
            print("  WARNING: --time or --mem still ??? — fill those in before submitting.")
        print("  Set record_lod=1 in config/ramp.cfg before submitting.")

    # ─────────────────────────────────────────────────────────────────────────
    # No action needed.
    # ─────────────────────────────────────────────────────────────────────────
    if not lod_seeds and not mc_crashed and not rerun_seeds and not debug_seeds:
        print()
        print("  All seeds completed without failures. No seeds evolved multicellularity.")

    print()
    print("=" * W)


if __name__ == "__main__":
    main()
