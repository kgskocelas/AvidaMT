#!/bin/bash
# Run from the experiment directory after script 14 (merge) completes.
# Moves data folders into a clean subdirectory layout:
#
#   original/
#     final/   <- final_entrench_*/
#     trans/   <- trans_entrench_*/
#   linear/    <- linear_final_*/, linear_trans_*/
#   narrow/    <- narrow_final_*/, narrow_trans_*/
#   merged/    <- already created by script 14
#
# Scripts, sbatch files, CSVs, and logs remain in place.

set -euo pipefail

mkdir -p original/final original/trans linear narrow

for d in final_entrench_*/;  do mv "$d" original/final/; done
for d in trans_entrench_*/;  do mv "$d" original/trans/; done
for d in linear_final_* linear_trans_*/; do [[ -d "$d" ]] && mv "$d" linear/; done
for d in narrow_final_* narrow_trans_*/; do [[ -d "$d" ]] && mv "$d" narrow/; done

echo "Done."
