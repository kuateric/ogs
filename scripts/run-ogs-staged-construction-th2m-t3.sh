#!/usr/bin/env bash
set -euo pipefail

# TH2M-T3 executes the loaded construction-equilibrium runtime derived from the
# authoritative T2D MFront/MGIS fresh-birth fixture. The runtime keeps the same
# physical t=2 reactivation target and uses the ordinary full TH2M operator.

test -f scripts/prepare-ogs-staged-construction-th2m-t3-runtime.py
python3 -m py_compile scripts/prepare-ogs-staged-construction-th2m-t3-runtime.py
python3 scripts/prepare-ogs-staged-construction-th2m-t3-runtime.py

# The upstream ExcavationTH2M fixture carries
# compensate_non_equilibrium_initial_residuum=true on displacement. OGS defines
# that option by storing the initial out-of-balance residual and subtracting it
# from every later Newton residual. That is useful when deliberately suppressing
# equilibration of an incompatible initial state, but it is incompatible with
# this T3 gate: T3 must restore construction equilibrium under the full physical
# operator and explicitly forbids residual homotopy/neutralization. Patch only
# the generated CI fixture so the ordinary physical residual is solved. No OGS
# production source, stiffness, material parameter, load, or physical time is
# changed.
python3 - <<'PY'
from pathlib import Path
p = Path('/tmp/run-th2m-t3.sh')
text = p.read_text(encoding='utf-8')
anchor = "tree.write(p, encoding='ISO-8859-1', xml_declaration=True)\nPY\n\nOGS_BIN="
replacement = (
    "# TH2M-T3J: do not neutralize the physical construction imbalance with the\n"
    "# inherited initial-residual compensation from ExcavationTH2M.\n"
    "comp = variables['displacement'].find('compensate_non_equilibrium_initial_residuum')\n"
    "if comp is None:\n"
    "    raise RuntimeError('TH2M-T3 displacement initial-residual compensation anchor missing')\n"
    "comp.text = 'false'\n\n"
    "tree.write(p, encoding='ISO-8859-1', xml_declaration=True)\n"
    "PY\n\n"
    "OGS_BIN="
)
if text.count(anchor) != 1:
    raise RuntimeError('TH2M-T3 generated project-write anchor changed')
text = text.replace(anchor, replacement, 1)
p.write_text(text, encoding='utf-8')
PY

bash -n /tmp/run-th2m-t3.sh
chmod +x /tmp/run-th2m-t3.sh
/tmp/run-th2m-t3.sh
