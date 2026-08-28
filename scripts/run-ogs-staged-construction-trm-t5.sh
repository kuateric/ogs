#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-trm-t5
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-trm-t5
cd ogs-trm-t5
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-trm-t2.py"
python3 "$ROOT/scripts/ogs-staged-construction-trm-t3.py"
python3 "$ROOT/scripts/ogs-staged-construction-trm-t5.py"
git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=ThermoRichardsMechanics'
cmake --build --preset release --target ProcessLib ThermoRichardsMechanics ogs --parallel 2

cp -a Tests/Data/ThermoRichardsMechanics/FullySaturatedFlowMechanics trm-t5-case
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu trm-t5-case/

python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('trm-t5-case/flow_fully_saturated.prj')
tree = ET.parse(p)
root = tree.getroot()
root.find('mesh').text = 'square_1x1_quad_1e1_2_matIDs.vtu'

process = root.find('./processes/process')
if process is None or (process.findtext('type') or '').strip() != 'THERMO_RICHARDS_MECHANICS':
    raise RuntimeError('canonical TRM process not found')

# Explicit per-MaterialID constitutive authority: host/material A uses E_A,
# newborn backfill/material B uses E_B. The lifecycle only carries id=5.
base_cr = process.find('constitutive_relation')
if base_cr is None:
    raise RuntimeError('canonical constitutive relation not found')
base_cr.set('id', '0')
cr1 = deepcopy(base_cr); cr1.set('id', '1'); process.append(cr1)
cr5 = deepcopy(base_cr); cr5.set('id', '5')
cr5.find('youngs_modulus').text = 'E_B'
process.append(cr5)

parameters = root.find('./parameters')
if parameters is None:
    raise RuntimeError('parameters block not found')
for prm in parameters.findall('parameter'):
    if (prm.findtext('name') or '').strip() == 'E':
        prm.find('name').text = 'E_A'
        break
else:
    raise RuntimeError('canonical E parameter not found')
par = ET.SubElement(parameters, 'parameter')
ET.SubElement(par, 'name').text = 'E_B'
ET.SubElement(par, 'type').text = 'Constant'
ET.SubElement(par, 'value').text = '2.5e9'
# Make A a 4x contrast to B while remaining in the canonical linear family.
for prm in parameters.findall('parameter'):
    if (prm.findtext('name') or '').strip() == 'E_A':
        prm.find('value').text = '1.0e10'
base_cr.find('youngs_modulus').text = 'E_A'
cr1.find('youngs_modulus').text = 'E_A'

medium = root.find('./media/medium')
if medium is None:
    raise RuntimeError('canonical medium not found')
medium.set('id', '0,1')
med5 = deepcopy(medium); med5.set('id', '5')
root.find('./media').append(med5)

variables = {(pv.findtext('name') or '').strip(): pv
             for pv in root.findall('./process_variables/process_variable')}
required = ('temperature', 'pressure', 'displacement')
if any(name not in variables for name in required):
    raise RuntimeError(f'unexpected TRM variables: {sorted(variables)}')

def make_deactivation():
    ds = ET.Element('deactivated_subdomains')
    d = ET.SubElement(ds, 'deactivated_subdomain')
    ti = ET.SubElement(d, 'time_interval')
    ET.SubElement(ti, 'start').text = '0'
    ET.SubElement(ti, 'end').text = '1'
    ET.SubElement(d, 'material_ids').text = '1'
    ET.SubElement(d, 'activation_material_id').text = '5'
    return ds

for name in required:
    pv = variables[name]
    ic = pv.find('initial_condition')
    pv.insert(list(pv).index(ic) + 1 if ic is not None else len(pv), make_deactivation())

# Explicit absolute placement values as already passed by T3.
def add_scalar(name, value):
    prm = ET.SubElement(parameters, 'parameter')
    ET.SubElement(prm, 'name').text = name
    ET.SubElement(prm, 'type').text = 'Constant'
    ET.SubElement(prm, 'value').text = str(value)
add_scalar('TRM_T5_PlacementPressure', 12345.0)
add_scalar('TRM_T5_PlacementTemperature', 310.15)
variables['pressure'].find('initial_condition').text = 'TRM_T5_PlacementPressure'
variables['temperature'].find('initial_condition').text = 'TRM_T5_PlacementTemperature'
for bc in variables['pressure'].findall('./boundary_conditions/boundary_condition'):
    bc.find('parameter').text = 'TRM_T5_PlacementPressure'
for bc in variables['temperature'].findall('./boundary_conditions/boundary_condition'):
    bc.find('parameter').text = 'TRM_T5_PlacementTemperature'

cc = root.find('./time_loop/processes/process/convergence_criterion')
if cc is None or (cc.findtext('type') or '').strip() != 'PerComponentDeltaX':
    raise RuntimeError('unexpected TRM convergence criterion')
if cc.find('reltols') is None:
    ET.SubElement(cc, 'reltols').text = '0 1e-14 0 0'

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p trm-t5-out
set +e
"$OGS_BIN" -o trm-t5-out trm-t5-case/flow_fully_saturated.prj > trm-t5.log 2>&1
rc=$?
set -e
cat trm-t5.log
if [ "$rc" -ne 0 ]; then
  echo "TRM-T5 material reassignment E2E failed with rc=$rc" >&2
  exit "$rc"
fi
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' trm-t5.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('trm-t5.log').read_text(errors='replace')
assign = [(int(e), int(m)) for e,m in re.findall(
    r'TRM-T5 activation material reassigned for element (\d+): material_id=(\d+)', log)]
bound = [(int(e), int(m)) for e,m in re.findall(
    r'TRM-T5 coupled birth material bound for element (\d+): material_id=(\d+)', log)]
fresh = [int(e) for e in re.findall(
    r'TRM-T2 fresh coupled birth state initialized for element (\d+)', log)]
if len(assign) != 6 or len(set(assign)) != 6 or any(m != 5 for _,m in assign):
    raise RuntimeError(f'bad TRM-T5 material assignments: {assign}')
if len(bound) != 6 or len(set(bound)) != 6 or any(m != 5 for _,m in bound):
    raise RuntimeError(f'bad TRM-T5 constitutive bindings: {bound}')
if len(fresh) != 6 or len(set(fresh)) != 6:
    raise RuntimeError(f'bad TRM-T5 fresh birth evidence: {fresh}')
if sorted(e for e,_ in bound) != sorted(set(fresh)):
    raise RuntimeError('TRM-T5 rebound material and fresh-state element sets differ')
if 'MFront: integration failed' in log:
    raise RuntimeError('unexpected MFront integration failure in linear T5 gate')
Path('../trm-t5-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=TRM_T5_material_reassignment\n'
    'material_A_id=0,1\nmaterial_B_id=5\n'
    'E_A=1e10\nE_B=2.5e9\n'
    f'assigned_elements={sorted(e for e,_ in assign)}\n'
    f'bound_elements={sorted(e for e,_ in bound)}\n'
    'fresh_state_from_new_material=true\n'
    'material_law_neutral_lifecycle=true\n'
    'full_physical_operator=true\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
