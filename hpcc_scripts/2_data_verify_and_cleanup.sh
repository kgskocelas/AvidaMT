#!/bin/bash
#
# experiment_cleanup.sh
#
# Run from the directory containing both experiment folders.
#
# Workflow:
#   1. Verify  — union of uni + multi seeds forms exactly 1000 consecutive seeds.
#   2. Remove  — delete uni experiment folders whose seed also exists in multi.
#   3. Cleanup — for all remaining experiment folders:
#        Uni   → delete lod-*.xml  |  gzip *.xml  |  delete ramp.cfg  |  delete mt_gls_detail.dat
#        Multi →                      gzip *.xml  |  delete ramp.cfg  |  delete mt_gls_detail.dat
#   4. Remove log files and flock lock files from both phase directories.
#   5. Remove config/ dirs (executable + ramp.cfg), 1_summarize_run_data.py, and README.md
#      from both phase directories.
#
# Without --delete : dry run, no changes made (step 3 preview skips would-be-removed uni folders)
# With    --delete : all operations are performed in sequence

# ── Configuration ─────────────────────────────────────────────────────────────
UNI_DIR="pop-regulation-uni"
MULTI_DIR="pop-regulation-multi"
# ──────────────────────────────────────────────────────────────────────────────

DELETE=false
[[ "$1" == "--delete" ]] && DELETE=true

shopt -s nullglob

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$UNI_DIR"   ]] || die "'$UNI_DIR' not found in current directory."
[[ -d "$MULTI_DIR" ]] || die "'$MULTI_DIR' not found in current directory."


# ── Collect seeds → associative arrays: 4-digit seed string → folder name ────

declare -A uni_map multi_map

for path in "$UNI_DIR"/*/; do
    f=$(basename "$path")
    [[ "$f" =~ ([0-9]{4})$ ]] && uni_map["${BASH_REMATCH[1]}"]="$f"
done

for path in "$MULTI_DIR"/*/; do
    f=$(basename "$path")
    [[ "$f" =~ ([0-9]{4})$ ]] && multi_map["${BASH_REMATCH[1]}"]="$f"
done

printf "Uni seeds   : %d  (%s)\n" "${#uni_map[@]}"   "$UNI_DIR"
printf "Multi seeds : %d  (%s)\n" "${#multi_map[@]}" "$MULTI_DIR"
echo ""


# ══════════════════════════════════════════════════════════════════════════════
echo "══ Step 1: Verify seed coverage ══════════════════════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

declare -A union_map
for s in "${!uni_map[@]}" "${!multi_map[@]}"; do union_map["$s"]=1; done
mapfile -t sorted_seeds < <(printf '%s\n' "${!union_map[@]}" | sort -n)
total=${#sorted_seeds[@]}

verify_ok=true

if [[ $total -ne 1000 ]]; then
    overlap=$(( ${#uni_map[@]} + ${#multi_map[@]} - total ))
    printf "FAIL [count] %d unique seeds across both folders (expected 1000).\n" "$total"
    printf "             Uni: %d  |  Multi: %d  |  Overlap: %d\n" \
        "${#uni_map[@]}" "${#multi_map[@]}" "$overlap"
    verify_ok=false
fi

if [[ $total -gt 0 ]]; then
    lo=${sorted_seeds[0]}
    hi=${sorted_seeds[-1]}
    span=$(( hi - lo + 1 ))
    if [[ $span -ne $total ]]; then
        printf "FAIL [gaps]  Range %s–%s spans %d slots but only %d unique seeds.\n" \
            "$lo" "$hi" "$span" "$total"
        prev=${sorted_seeds[0]}
        for s in "${sorted_seeds[@]:1}"; do
            gap=$(( s - prev ))
            [[ $gap -gt 1 ]] && printf "             Gap: %s → %s  (%d missing)\n" \
                "$prev" "$s" $(( gap - 1 ))
            prev=$s
        done
        verify_ok=false
    fi
fi

$verify_ok || { echo ""; die "Seed coverage check failed. Aborting."; }

remaining_uni=0
for s in "${!uni_map[@]}"; do [[ -z "${multi_map[$s]+_}" ]] && (( remaining_uni++ )); done

printf "PASS Seeds %s–%s (%d consecutive).\n" "${sorted_seeds[0]}" "${sorted_seeds[-1]}" "$total"
printf "     After step 2: %d uni  +  %d multi  =  1000 ✓\n" "$remaining_uni" "${#multi_map[@]}"
echo ""


# ══════════════════════════════════════════════════════════════════════════════
echo "══ Step 2: Remove overlapping uni seeds ══════════════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

step2_removed=0
step2_skipped=0
for s in $(printf '%s\n' "${!multi_map[@]}" | sort -n); do
    [[ -n "${uni_map[$s]+_}" ]] || continue
    uni_folder="$UNI_DIR/${uni_map[$s]}"
    multi_folder="$MULTI_DIR/${multi_map[$s]}"

    # Safety check: every file in the uni folder must exist by name in multi
    missing_in_multi=()
    while IFS= read -r -d '' uni_file; do
        fname=$(basename "$uni_file")
        [[ -e "$multi_folder/$fname" ]] || missing_in_multi+=("$fname")
    done < <(find "$uni_folder" -maxdepth 1 -type f -print0)

    if [[ ${#missing_in_multi[@]} -gt 0 ]]; then
        (( step2_skipped++ ))
        printf "  SKIPPED: %s\n" "$uni_folder"
        printf "           %d file(s) present in uni but not found in %s:\n" \
            "${#missing_in_multi[@]}" "$multi_folder"
        for f in "${missing_in_multi[@]}"; do
            printf "             %s\n" "$f"
        done
        continue
    fi

    (( step2_removed++ ))
    if $DELETE; then
        rm -rf "$uni_folder"
        printf "  Deleted:      %s\n" "$uni_folder"
    else
        printf "  Would delete: %s\n" "$uni_folder"
    fi
done

if [[ $step2_removed -eq 0 && $step2_skipped -eq 0 ]]; then
    echo "  No overlapping seeds found between the two folders."
else
    printf "  → %d folder(s) %s.\n" "$step2_removed" \
        "$($DELETE && echo 'deleted' || echo 'would be deleted')"
    [[ $step2_skipped -gt 0 ]] && \
        printf "  → %d folder(s) skipped due to missing files in multi (see above).\n" "$step2_skipped"
fi
echo ""


# ══════════════════════════════════════════════════════════════════════════════
echo "══ Step 3: Clean up experiment folders ════════════════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

total_gzipped=0
total_deleted=0

cleanup_folder() {
    local dir="$1"
    local is_uni="$2"   # true | false
    local folder; folder=$(basename "$dir")
    local changed=false

    echo "── $folder"

    # ① Delete lod-*.xml (uni only)
    if [[ "$is_uni" == true ]]; then
        local lods=("$dir"/lod-*.xml)
        if [[ ${#lods[@]} -gt 0 ]]; then
            changed=true
            (( total_deleted += ${#lods[@]} ))
            if $DELETE; then
                rm -f "${lods[@]}"
                printf "   [deleted]      %d lod xml(s)\n" "${#lods[@]}"
            else
                printf "   [would delete] %d lod xml(s)\n" "${#lods[@]}"
            fi
        fi
    fi

    # ② Gzip any uncompressed *.xml (uni: skip lod-*.xml already handled above)
    local xmls=()
    if [[ "$is_uni" == true ]]; then
        mapfile -t xmls < <(find "$dir" -maxdepth 1 -name "*.xml" ! -name "lod-*.xml" 2>/dev/null)
    else
        mapfile -t xmls < <(find "$dir" -maxdepth 1 -name "*.xml" 2>/dev/null)
    fi
    if [[ ${#xmls[@]} -gt 0 ]]; then
        changed=true
        (( total_gzipped += ${#xmls[@]} ))
        if $DELETE; then
            if command -v pigz &>/dev/null; then
                pigz -p 8 "${xmls[@]}"
            else
                gzip "${xmls[@]}"
            fi
            printf "   [gzipped]      %d xml(s)\n" "${#xmls[@]}"
        else
            printf "   [would gzip]   %d xml(s)\n" "${#xmls[@]}"
        fi
    fi

    # ③ Delete ramp.cfg (both)
    if [[ -f "$dir/ramp.cfg" ]]; then
        changed=true
        (( total_deleted++ ))
        if $DELETE; then
            rm -f "$dir/ramp.cfg"
            echo "   [deleted]      ramp.cfg"
        else
            echo "   [would delete] ramp.cfg"
        fi
    fi


    $changed || echo "   (nothing to do)"
}

# Uni folders — in dry-run, skip seeds that would have been deleted in step 2
echo ""
echo "  ── $UNI_DIR"
echo ""
for path in "$UNI_DIR"/*/; do
    [[ -d "$path" ]] || continue
    f=$(basename "$path")
    [[ "$f" =~ ([0-9]{4})$ ]] || continue
    seed="${BASH_REMATCH[1]}"
    [[ -n "${multi_map[$seed]+_}" ]] && continue   # skip removed/would-be-removed seeds
    cleanup_folder "$path" true
done

# Multi folders
echo ""
echo "  ── $MULTI_DIR"
echo ""
for path in "$MULTI_DIR"/*/; do
    [[ -d "$path" ]] || continue
    f=$(basename "$path")
    [[ "$f" =~ [0-9]{4}$ ]] || continue
    cleanup_folder "$path" false
done


# ══════════════════════════════════════════════════════════════════════════════
echo "══ Step 4: Remove log files and flock lock files ══════════════════════════"
# ══════════════════════════════════════════════════════════════════════════════

total_logs_deleted=0
total_locks_deleted=0

for phase_dir in "$UNI_DIR" "$MULTI_DIR"; do
    [[ -d "$phase_dir" ]] || continue

    logs=("$phase_dir"/*.log)
    if [[ ${#logs[@]} -gt 0 ]]; then
        (( total_logs_deleted += ${#logs[@]} ))
        if $DELETE; then
            rm -f "${logs[@]}"
            printf "  [deleted]      %d log file(s) from %s\n" "${#logs[@]}" "$phase_dir"
        else
            printf "  [would delete] %d log file(s) from %s\n" "${#logs[@]}" "$phase_dir"
        fi
    fi

    locks=("$phase_dir"/*.lock)
    if [[ ${#locks[@]} -gt 0 ]]; then
        (( total_locks_deleted += ${#locks[@]} ))
        if $DELETE; then
            rm -f "${locks[@]}"
            printf "  [deleted]      %d flock .lock file(s) from %s\n" "${#locks[@]}" "$phase_dir"
        else
            printf "  [would delete] %d flock .lock file(s) from %s\n" "${#locks[@]}" "$phase_dir"
        fi
    fi
done

txts=("$UNI_DIR"/*.txt "$MULTI_DIR"/*.txt)
txt_count=0
for f in "${txts[@]}"; do [[ -e "$f" ]] && (( txt_count++ )); done
if [[ $txt_count -gt 0 ]]; then
    printf "\n  NOTE: %d flock .txt file(s) found (resource usage summaries) — not deleted.\n" "$txt_count"
    printf "        Remove manually before tarring if you don't want them included.\n"
fi
echo ""


# ══════════════════════════════════════════════════════════════════════════════
echo "══ Step 5: Remove executables, scripts, READMEs, and next-array.txt ════════"
# ══════════════════════════════════════════════════════════════════════════════

total_infra_deleted=0
EXECUTABLES=(mt_lr_gls mt_lr_gls_dol_control ts_mt)

for phase_dir in "$UNI_DIR" "$MULTI_DIR"; do
    [[ -d "$phase_dir" ]] || continue

    # Executables in config/ (leave ramp.cfg in place)
    for exe in "${EXECUTABLES[@]}"; do
        if [[ -f "$phase_dir/config/$exe" ]]; then
            (( total_infra_deleted++ ))
            if $DELETE; then
                rm -f "$phase_dir/config/$exe"
                printf "  [deleted]      %s/config/%s\n" "$phase_dir" "$exe"
            else
                printf "  [would delete] %s/config/%s\n" "$phase_dir" "$exe"
            fi
        fi
    done

    for fname in 1_summarize_run_data.py README.md next-array.txt; do
        if [[ -f "$phase_dir/$fname" ]]; then
            (( total_infra_deleted++ ))
            if $DELETE; then
                rm -f "$phase_dir/$fname"
                printf "  [deleted]      %s/%s\n" "$phase_dir" "$fname"
            else
                printf "  [would delete] %s/%s\n" "$phase_dir" "$fname"
            fi
        fi
    done
done
echo ""


# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
printf "Uni folders removed  : %d\n" "$step2_removed"
printf "Uni folders skipped  : %d  (file mismatch — check warnings above)\n" "$step2_skipped"
printf "XMLs gzipped         : %d\n" "$total_gzipped"
printf "Other files deleted  : %d\n" "$total_deleted"
printf "Log files deleted    : %d\n" "$total_logs_deleted"
printf "Lock files deleted   : %d\n" "$total_locks_deleted"
printf "Infra files deleted  : %d  (executables, scripts, READMEs, next-array.txt)\n" "$total_infra_deleted"
if ! $DELETE; then
    echo ""
    echo "Dry run complete. Re-run with --delete to apply all changes."
fi
