#!/usr/bin/env bash
set -euo pipefail

# TH2M-T3 executes the loaded construction-equilibrium runtime derived from the
# authoritative T2D MFront/MGIS fresh-birth fixture. The runtime keeps the same
# physical t=2 reactivation target and uses the ordinary full TH2M operator.

test -f scripts/prepare-ogs-staged-construction-th2m-t3-runtime.py
python3 -m py_compile scripts/prepare-ogs-staged-construction-th2m-t3-runtime.py
python3 scripts/prepare-ogs-staged-construction-th2m-t3-runtime.py
bash -n /tmp/run-th2m-t3.sh
chmod +x /tmp/run-th2m-t3.sh
/tmp/run-th2m-t3.sh
