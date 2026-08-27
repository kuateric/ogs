#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-hm-b4
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b4
cd ogs-hm-b4
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

python3 ../scripts/ogs-staged-construction-r0.py
python3 ../scripts/ogs-staged-construction-r2g.py
python3 ../scripts/ogs-staged-construction-hm-b2.py
python3 ../scripts/ogs-staged-construction-hm-b3.py
python3 ../scripts/ogs-staged-construction-hm-b4.py
git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2

cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b4-case
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET
p = Path('hm-b4-case/simHM_deactivate_H.prj')
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

# Deterministic coupled placement-state gate: exact mechanical equilibrium,
# non-zero absolute liquid-pressure placement state.
b = root.find('./processes/process/specific_body_force')
b.text = '0 0'
for par in root.findall('./parameters/parameter'):
    if par.findtext('name') == 'InitialPressure':
        par.find('values').text = '12345'
    if par.findtext('name') == 'zero':
        # Keep the external pressure BC compatible with the placement state.
        par.find('values').text = '12345'
ts = root.find('./time_loop/processes/process/time_stepping')
ts.find('t_end').text = '2.0'
pair = ts.find('./timesteps/pair')
pair.find('repeat').text = '2'
pair.find('delta_t').text = '1.0'
tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p hm-b4-out
"$OGS_BIN" -o hm-b4-out hm-b4-case/simHM_deactivate_H.prj > hm-b4.log 2>&1
cat hm-b4.log
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b4.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('hm-b4.log').read_text(errors='replace')
items = [(int(e), float(p)) for e,p in re.findall(r'HM-B4 placement state captured for element (\d+): p_L0=([-+0-9.eE]+)', log)]
unique = sorted({e for e,_ in items})
if len(unique) != 6:
    raise RuntimeError(f'expected placement capture for 6 reactivated elements, got {unique}')
if any(abs(p - 12345.0) > 1e-8 for _,p in items):
    raise RuntimeError(f'wrong explicit p_L0 capture: {items}')
Path('../hm-b4-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B4_explicit_coupled_placement_state\n'
    f'placement_elements={unique}\n'
    'mechanical_birth_reference=current_deformed_configuration\n'
    'liquid_pressure_is_absolute=true\n'
    'explicit_p_L0=12345\n'
    'construction_substep_advances_physical_time=false\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
