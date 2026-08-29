#!/usr/bin/env bash
set -euo pipefail

# TH2M-T2C is intentionally derived from the already authoritative T1B lifecycle
# fixture. It adds the compiled T2B fresh-birth implementation and requires the
# runtime to prove that every reactivated element gets both a fresh constitutive
# birth event and a last-converged displacement reference before successful solve.
# This gate stays material-law neutral; MFront/MGIS history safety is T2D.

base="scripts/run-ogs-staged-construction-th2m-t1b.sh"
t2b="scripts/ogs-staged-construction-th2m-t2b-fresh-birth-runtime.py"
test -f "$base"
test -f "$t2b"
cp "$t2b" /tmp/th2m-t2b-runtime.py

python3 - <<'PY'
from pathlib import Path
src = Path('scripts/run-ogs-staged-construction-th2m-t1b.sh').read_text(encoding='utf-8')

# Keep the proven T1B fixture semantics, but isolate paths/evidence and apply the
# T2B production patch immediately after the exact canonical checkout.
src = src.replace('TH2M-T1B', 'TH2M-T2C').replace('th2m-t1b', 'th2m-t2c').replace('TH2M_T1B', 'TH2M_T2C')
needle = '''test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"\n\n# T1A proved'''
insert = '''test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"\npython3 /tmp/th2m-t2b-runtime.py\ngit diff --check\n\n# T1A proved'''
if src.count(needle) != 1:
    raise RuntimeError('T2C canonical-checkout injection anchor changed')
src = src.replace(needle, insert, 1)

# Extend the final evidence assertion with the fresh-birth lifecycle logs emitted
# by the T2B implementation. The reactivated set found from real local assembly
# must exactly be covered by both state-reset and u_birth-reference events.
needle = """reactivated = a2 - a1\nif len(reactivated) == 0:\n    raise RuntimeError('no TH2M elements reactivated')\nPath('../th2m-t2c-evidence.txt').write_text(\n"""
insert = """reactivated = a2 - a1\nif len(reactivated) == 0:\n    raise RuntimeError('no TH2M elements reactivated')\nborn = {int(x) for x in re.findall(r'TH2M fresh-birth state initialized for element (\\d+) at t=2(?:\\.0+)?', log)}\nreferenced = {int(x) for x in re.findall(r'TH2M stress-free birth reference captured for element (\\d+)', log)}\nif not reactivated <= born:\n    raise RuntimeError(f'missing fresh constitutive birth events: reactivated={sorted(reactivated)} born={sorted(born)}')\nif not reactivated <= referenced:\n    raise RuntimeError(f'missing u_birth captures: reactivated={sorted(reactivated)} referenced={sorted(referenced)}')\nPath('../th2m-t2c-evidence.txt').write_text(\n"""
if src.count(needle) != 1:
    raise RuntimeError('T2C evidence anchor changed')
src = src.replace(needle, insert, 1)

needle = """    f'reactivated_elements={sorted(reactivated)}\\n'\n    'gas_capillary_temperature_displacement_lifecycle=synchronized\\n'\n"""
insert = """    f'reactivated_elements={sorted(reactivated)}\\n'\n    f'fresh_birth_state_events={sorted(born)}\\n'\n    f'last_converged_reference_events={sorted(referenced)}\\n'\n    'birth_stress=zero_unless_explicit_placement_state\\n'\n    'physical_stiffness=full_from_first_active_assembly\\n'\n    'gas_capillary_temperature_displacement_lifecycle=synchronized\\n'\n"""
if src.count(needle) != 1:
    raise RuntimeError('T2C evidence-field anchor changed')
src = src.replace(needle, insert, 1)

Path('/tmp/run-th2m-t2c.sh').write_text(src, encoding='utf-8')
PY

chmod +x /tmp/run-th2m-t2c.sh
/tmp/run-th2m-t2c.sh
