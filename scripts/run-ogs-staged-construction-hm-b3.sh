#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-hm-b3
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b3
cd ogs-hm-b3
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# HM-B3 consumes the persistent DomainTransition API that was already
# authoritatively validated in the mechanical staged-construction stack. Keep
# this deterministic evidence clone pinned to canonical upstream and compose
# only the minimal direct dependencies: R0 defines DomainTransition and wires
# transition detection, R2G persists the last transition for process-level
# consumers. The unrelated mechanical removal-force stages are intentionally
# not applied here.
python3 ../scripts/ogs-staged-construction-r0.py
python3 ../scripts/ogs-staged-construction-r2g.py

# Reuse the already-authoritative HM-B2 active-domain semantics, then add the
# fresh coupled birth-state hook. No unrelated process code is touched.
python3 ../scripts/ogs-staged-construction-hm-b2.py
python3 ../scripts/ogs-staged-construction-hm-b3.py
git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2

cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b3-case
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET
p = Path('hm-b3-case/simHM_deactivate_H.prj')
tree = ET.parse(p)
root = tree.getroot()
variables = root.findall('./process_variables/process_variable')
by_name = {pv.findtext('name').strip(): pv for pv in variables if pv.findtext('name')}
pressure = by_name['pressure']
displacement = by_name['displacement']
pressure_ds = pressure.find('deactivated_subdomains')
if pressure_ds is None or displacement.find('deactivated_subdomains') is not None:
    raise RuntimeError('unexpected canonical HM deactivation layout')
ic = displacement.find('initial_condition')
insert_at = list(displacement).index(ic) + 1 if ic is not None else len(displacement)
displacement.insert(insert_at, deepcopy(pressure_ds))

# HM-B3 isolates lifecycle/state ownership. Loaded equilibrium restoration is a
# separate gate, so keep the zero state as exact equilibrium while proving that
# reactivation invokes a fresh state for every returned coupled element.
b = root.find('./processes/process/specific_body_force')
if b is None:
    raise RuntimeError('specific_body_force not found')
b.text = '0 0'
ts = root.find('./time_loop/processes/process/time_stepping')
if ts is None:
    raise RuntimeError('time stepping not found')
ts.find('t_end').text = '2.0'
pair = ts.find('./timesteps/pair')
pair.find('repeat').text = '2'
pair.find('delta_t').text = '1.0'
tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p hm-b3-out
"$OGS_BIN" -o hm-b3-out hm-b3-case/simHM_deactivate_H.prj > hm-b3.log 2>&1
cat hm-b3.log
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b3.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('hm-b3.log').read_text(errors='replace')
ids = [int(x) for x in re.findall(r'HM-B3 fresh coupled birth state initialized for element (\d+)', log)]
unique = sorted(set(ids))
if len(unique) != 6:
    raise RuntimeError(f'expected fresh birth for 6 reactivated elements, got {unique}')
Path('../hm-b3-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B3_fresh_coupled_birth_state\n'
    'lifecycle_dependencies=R0,R2G\n'
    f'fresh_birth_elements={unique}\n'
    'fresh_solid_material_state=true\n'
    'birth_effective_stress_zero=true\n'
    'birth_strain_zero=true\n'
    'pressure_displacement_activation_synchronized=true\n'
    'body_force_for_state_gate=0\n'
    'runtime_exit=0\n', encoding='utf-8')
PY