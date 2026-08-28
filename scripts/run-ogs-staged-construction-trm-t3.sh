#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-trm-t3
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-trm-t3
cd ogs-trm-t3
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-trm-t2.py"
python3 "$ROOT/scripts/ogs-staged-construction-trm-t3.py"
git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=ThermoRichardsMechanics'
cmake --build --preset release --target ProcessLib ThermoRichardsMechanics ogs --parallel 2

cp -a Tests/Data/ThermoRichardsMechanics/FullySaturatedFlowMechanics trm-t3-case
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu trm-t3-case/

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('trm-t3-case/flow_fully_saturated.prj')
tree = ET.parse(p)
root = tree.getroot()
root.find('mesh').text = 'square_1x1_quad_1e1_2_matIDs.vtu'
medium = root.find('./media/medium')
if medium is None:
    raise RuntimeError('canonical TRM medium not found')
medium.set('id', '0,1')

variables = root.findall('./process_variables/process_variable')
by_name = {(pv.findtext('name') or '').strip(): pv for pv in variables}
required = ('temperature', 'pressure', 'displacement')
if any(name not in by_name for name in required):
    raise RuntimeError(f'unexpected TRM variables: {sorted(by_name)}')

def make_deactivation():
    ds = ET.Element('deactivated_subdomains')
    d = ET.SubElement(ds, 'deactivated_subdomain')
    ti = ET.SubElement(d, 'time_interval')
    ET.SubElement(ti, 'start').text = '0'
    ET.SubElement(ti, 'end').text = '1'
    ET.SubElement(d, 'material_ids').text = '1'
    return ds

for name in required:
    pv = by_name[name]
    if pv.find('deactivated_subdomains') is not None:
        raise RuntimeError(f'{name} unexpectedly already restricted')
    ic = pv.find('initial_condition')
    pv.insert(list(pv).index(ic) + 1 if ic is not None else len(pv), make_deactivation())

parameters = root.find('./parameters')
if parameters is None:
    raise RuntimeError('parameters block not found')

def add_scalar_parameter(name, value):
    prm = ET.SubElement(parameters, 'parameter')
    ET.SubElement(prm, 'name').text = name
    ET.SubElement(prm, 'type').text = 'Constant'
    ET.SubElement(prm, 'value').text = str(value)

add_scalar_parameter('TRM_T3_PlacementPressure', 12345.0)
add_scalar_parameter('TRM_T3_PlacementTemperature', 310.15)

by_name['pressure'].find('initial_condition').text = 'TRM_T3_PlacementPressure'
by_name['temperature'].find('initial_condition').text = 'TRM_T3_PlacementTemperature'

for bc in by_name['pressure'].findall('./boundary_conditions/boundary_condition'):
    bc.find('parameter').text = 'TRM_T3_PlacementPressure'
for bc in by_name['temperature'].findall('./boundary_conditions/boundary_condition'):
    bc.find('parameter').text = 'TRM_T3_PlacementTemperature'

# Preserve all mechanical supports exactly at zero; unlike the hydraulic and
# thermal placement parameters, no shared mechanics parameter is repurposed.
for bc in by_name['displacement'].findall('./boundary_conditions/boundary_condition'):
    if (bc.findtext('parameter') or '').strip() != 'dirichlet0':
        raise RuntimeError('unexpected nonzero displacement support in T3 fixture')

# The canonical fixture uses absolute-only PerComponentDeltaX tolerances.
# Raising the absolute pressure level from O(1) to 12345 Pa leaves the Newton
# correction at roundoff (~2.5e-12 Pa) but above the inherited absolute pressure
# tolerance 1e-14 Pa. OGS' established PerComponentDeltaX criterion accepts
# absolute OR relative convergence. Add a pressure-only reltol of 1e-14; all
# original absolute tolerances remain unchanged and the other components retain
# no relative shortcut. This is scale-aware convergence, not a physics or gate
# relaxation.
cc = root.find('./time_loop/processes/process/convergence_criterion')
if cc is None or (cc.findtext('type') or '').strip() != 'PerComponentDeltaX':
    raise RuntimeError('unexpected TRM convergence criterion')
if cc.find('reltols') is not None:
    raise RuntimeError('canonical TRM fixture unexpectedly already has reltols')
reltols = ET.SubElement(cc, 'reltols')
reltols.text = '0 1e-14 0 0'

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p trm-t3-out
set +e
"$OGS_BIN" -o trm-t3-out trm-t3-case/flow_fully_saturated.prj > trm-t3.log 2>&1
rc=$?
set -e
cat trm-t3.log
if [ "$rc" -ne 0 ]; then
  echo "TRM-T3 explicit coupled placement-state E2E failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' trm-t3.log

python3 - <<'PY'
from pathlib import Path
import math
import re

log = Path('trm-t3.log').read_text(errors='replace')
fresh = [int(x) for x in re.findall(
    r'TRM-T2 fresh coupled birth state initialized for element (\d+)', log)]
pat = re.compile(
    r'TRM-T3 placement state captured for element (\d+): '
    r'T0=([^,]+), p_L0=([^\s]+)')
placements = [(int(e), float(T), float(p)) for e, T, p in pat.findall(log)]

fresh_unique = sorted(set(fresh))
placement_unique = sorted({e for e, _, _ in placements})
if len(fresh_unique) != 6 or len(fresh) != 6:
    raise RuntimeError(f'expected six exactly-once fresh births, got {fresh}')
if len(placement_unique) != 6 or len(placements) != 6:
    raise RuntimeError(f'expected six exactly-once placement captures, got {placements}')
if fresh_unique != placement_unique:
    raise RuntimeError('fresh-state and placement-state element sets differ')
for e, T, p in placements:
    if not math.isclose(T, 310.15, rel_tol=0.0, abs_tol=1e-10):
        raise RuntimeError(f'element {e}: unexpected T0={T}')
    if not math.isclose(p, 12345.0, rel_tol=0.0, abs_tol=1e-8):
        raise RuntimeError(f'element {e}: unexpected p_L0={p}')
if 'MFront: integration failed' in log:
    raise RuntimeError('MFront integration failure during TRM-T3')

Path('../trm-t3-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=TRM_T3_explicit_coupled_placement_state\n'
    f'fresh_birth_elements={fresh_unique}\n'
    f'placement_elements={placement_unique}\n'
    'mechanical_birth_reference=current_deformed_configuration\n'
    'birth_stress=zero\n'
    'p_L0=12345\n'
    'T0=310.15\n'
    'pressure_semantics=absolute_primary_variable\n'
    'temperature_semantics=absolute_primary_variable\n'
    'full_physical_operator=true\n'
    'pressure_relative_convergence_tolerance=1e-14\n'
    'physical_time_advanced_by_construction=false\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
