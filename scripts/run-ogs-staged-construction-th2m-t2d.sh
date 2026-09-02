#!/usr/bin/env bash
set -euo pipefail

# TH2M-T2D extends the authoritative T2C fresh-birth runtime with a real
# MFront/MGIS constitutive law. All probes are CI-only; the production fresh-
# birth implementation remains material-law neutral.

test -f scripts/run-ogs-staged-construction-th2m-t1b.sh
test -f scripts/run-ogs-staged-construction-th2m-t2c.sh
test -f scripts/prepare-ogs-staged-construction-th2m-t2d.py
test -f scripts/instrument-ogs-staged-construction-th2m-t2d-mfront.py

python3 scripts/prepare-ogs-staged-construction-th2m-t2d.py
bash -n /tmp/run-th2m-t2d.sh
chmod +x /tmp/run-th2m-t2d.sh
/tmp/run-th2m-t2d.sh
