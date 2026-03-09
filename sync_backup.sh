#!/usr/bin/env bash
set -euo pipefail

SRC="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
DST="/home/omel305g/hpc_kg_balanced"

mkdir -p "$DST"

# SAFE sync (no deletions in backup)
rsync -aH --info=progress2 \
  --exclude='.git/' \
  "$SRC/" "$DST/"

echo "Backup sync complete: $SRC -> $DST"
