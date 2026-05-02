#!/bin/bash
#
# 0_new_experiment_setup.sh
#
# Creates the standard two-phase experiment directory structure.
# Run from the directory where you want the experiment folder created
# (typically /mnt/gs21/scratch/groups/devolab/Avida4).
#
# Usage: bash /path/to/0_new_experiment_setup.sh <experiment-name>

SCRIPTS_DIR="/mnt/gs21/scratch/groups/devolab/Avida4/analysis-scripts"

NAME="$1"
if [[ -z "$NAME" ]]; then
    echo "Usage: bash 0_new_experiment_setup.sh <experiment-name>" >&2
    exit 1
fi

UNI="${NAME}-uni"
MULTI="${NAME}-multi"

if [[ -d "$NAME" ]]; then
    echo "ERROR: '$NAME' already exists in $(pwd)." >&2
    exit 1
fi

echo "Creating experiment: $NAME"
echo "  Uni dir:   $UNI"
echo "  Multi dir: $MULTI"
echo ""

# ── Create directory structure ─────────────────────────────────────────────────
mkdir -p "$NAME/$UNI/config"
mkdir -p "$NAME/$MULTI/config"

# ── Create placeholder config and sbatch files ────────────────────────────────
touch "$NAME/$UNI/config/ramp.cfg"
touch "$NAME/$MULTI/config/ramp.cfg"
touch "$NAME/$UNI/${NAME}-base-run.sbatch"
touch "$NAME/$MULTI/${NAME}-rerun-mcs-w-lod-on.sbatch"

# ── Copy script 1 into both subdirectories ────────────────────────────────────
for dir in "$NAME/$UNI" "$NAME/$MULTI"; do
    cp "$SCRIPTS_DIR/1_summarize_run_data.py" "$dir/"
done

# ── Copy script 2, pre-fill UNI_DIR and MULTI_DIR ─────────────────────────────
cp "$SCRIPTS_DIR/2_data_verify_and_cleanup.sh" "$NAME/"
sed -i "s|^UNI_DIR=.*|UNI_DIR=\"$UNI\"|"     "$NAME/2_data_verify_and_cleanup.sh"
sed -i "s|^MULTI_DIR=.*|MULTI_DIR=\"$MULTI\"|" "$NAME/2_data_verify_and_cleanup.sh"
chmod +x "$NAME/2_data_verify_and_cleanup.sh"

# ── Copy script 3, pre-fill BASE_DIR and PREFIX ───────────────────────────────
cp "$SCRIPTS_DIR/3_tar_uni_and_multi_folders.sbatch" "$NAME/"
sed -i "s|^BASE_DIR=.*|BASE_DIR=\"$(pwd)/$NAME\"|" "$NAME/3_tar_uni_and_multi_folders.sbatch"
sed -i "s|^PREFIX=.*|PREFIX=\"$NAME\"|"            "$NAME/3_tar_uni_and_multi_folders.sbatch"

# ── Write parent README ────────────────────────────────────────────────────────
cat > "$NAME/README.md" << PARENTREADME
# $NAME

Two-phase entrenchment experiment.

## Directory structure

    $NAME/
    ├── $UNI/
    │   ├── config/
    │   │   └── ramp.cfg
    │   ├── ${NAME}-base-run.sbatch
    │   └── 1_summarize_run_data.py
    ├── $MULTI/
    │   ├── config/
    │   │   └── ramp.cfg           (set record_lod=1 before Phase 2)
    │   ├── ${NAME}-rerun-mcs-w-lod-on.sbatch
    │   └── 1_summarize_run_data.py
    ├── 2_data_verify_and_cleanup.sh
    ├── 3_tar_uni_and_multi_folders.sbatch
    └── README.md

## Workflow

### Phase 1 — Base runs

1. Fill in $UNI/config/ramp.cfg and copy in the executable
2. Fill in $UNI/${NAME}-base-run.sbatch
3. Submit and monitor
4. After completion, run from inside $UNI/:
       python3 1_summarize_run_data.py

### Phase 2 — MC rerun with LOD on

1. Fill in $MULTI/config/ramp.cfg (set record_lod=1) and copy in the executable
2. Fill in $MULTI/${NAME}-rerun-mcs-w-lod-on.sbatch
3. Set --array= using seeds from $UNI/next-array.txt
4. Submit and monitor
5. After completion, run from inside $MULTI/:
       python3 1_summarize_run_data.py

### Cleanup

Run from this directory ($NAME/):

    bash 2_data_verify_and_cleanup.sh           # dry run first
    bash 2_data_verify_and_cleanup.sh --delete  # apply

### Tar for Peter

Run from this directory ($NAME/):

    sbatch 3_tar_uni_and_multi_folders.sbatch
PARENTREADME

# ── Write uni README ───────────────────────────────────────────────────────────
cat > "$NAME/$UNI/README.md" << UNIREADME
# $UNI — Phase 1: Base Runs

Run all seeds here with LOD recording disabled (record_lod=0 or omitted from cfg).

## Setup checklist

- [ ] Fill in config/ramp.cfg   (record_lod should be 0 or absent)
- [ ] Copy executable into config/
- [ ] Fill in ${NAME}-base-run.sbatch
- [ ] Set --array= to your full seed range
- [ ] Submit

## After jobs finish

Run from this directory:

    python3 1_summarize_run_data.py

Then follow the action plan it prints. Use the --array value from
next-array.txt in ../$MULTI/${NAME}-rerun-mcs-w-lod-on.sbatch.
UNIREADME

# ── Write multi README ─────────────────────────────────────────────────────────
cat > "$NAME/$MULTI/README.md" << MULTIREADME
# $MULTI — Phase 2: MC Rerun with LOD On

Reruns only the seeds that evolved multicellularity (MC=T from Phase 1), with record_lod=1.

## Setup checklist

- [ ] Fill in config/ramp.cfg and set record_lod=1
- [ ] Copy executable into config/
- [ ] Fill in ${NAME}-rerun-mcs-w-lod-on.sbatch
- [ ] Set --array= using seeds from ../$UNI/next-array.txt
- [ ] Submit

## After jobs finish

Run from this directory:

    python3 1_summarize_run_data.py

Then return to ../ and run the cleanup script.
MULTIREADME

# ── Set group ownership and permissions for devolab ───────────────────────────
chgrp -R devolab "$NAME"
find "$NAME" -type d -exec chmod g+rwxs {} \;
find "$NAME" -type f -exec chmod g+rw  {} \;

# ── Summary ────────────────────────────────────────────────────────────────────
echo "Done. Created:"
echo "  $NAME/"
echo "  $NAME/$UNI/     (config/ with ramp.cfg placeholder, sbatch placeholder, script 1, README)"
echo "  $NAME/$MULTI/   (config/ with ramp.cfg placeholder, sbatch placeholder, script 1, README)"
echo "  $NAME/2_data_verify_and_cleanup.sh   (pre-filled)"
echo "  $NAME/3_tar_uni_and_multi_folders.sbatch  (pre-filled)"
echo "  $NAME/README.md"
echo ""
echo "Next: fill in config/ramp.cfg and sbatch files. See $NAME/README.md for the full workflow."
