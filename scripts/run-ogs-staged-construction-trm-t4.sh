#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-trm-t4
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-trm-t4
cd ogs-trm-t4
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# Reuse only the already-authoritatively-passed lifecycle/birth architecture.
# T4 introduces no new constitutive or continuation mechanism.
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

cp -a Tests/Data/ThermoRichardsMechanics/FullySaturatedFlowMechanics trm-t4-case
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu trm-t4-case/

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('trm-t4-case/flow_fully_saturated.prj')
tree = ET.parse(p)
root = tree.getroot()
root.find('mesh').text = 'square_1x1_quad_1e1_2_matIDs.vtu'

process = root.find('./processes/process')
if process is None or (process.findtext('type') or '').strip() != 'THERMO_RICHARDS_MECHANICS':
    raise RuntimeError('canonical TRM process not found')
body_force = process.find('specific_body_force')
if body_force is None or (body_force.text or '').strip() != '0 0':
    raise RuntimeError('unexpected canonical TRM body force')
body_force.text = '0 -9.81'

medium = root.find('./media/medium')
if medium is None:
    raise RuntimeError('canonical TRM medium not found')
medium.set('id', '0,1')

# Give the loaded gate a physically meaningful solid weight while preserving
# all constitutive stiffness/coupling operators at their full physical values.
solid_density = medium.find("./phases/phase[type='Solid']/properties/property[name='density']/value")
if solid_density is None:
    raise RuntimeError('solid density not found')
solid_density.text = '2000'

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

add_scalar_parameter('TRM_T4_PlacementPressure', 12345.0)
add_scalar_parameter('TRM_T4_PlacementTemperature', 310.15)
by_name['pressure'].find('initial_condition').text = 'TRM_T4_PlacementPressure'
by_name['temperature'].find('initial_condition').text = 'TRM_T4_PlacementTemperature'
for bc in by_name['pressure'].findall('./boundary_conditions/boundary_condition'):
    bc.find('parameter').text = 'TRM_T4_PlacementPressure'
for bc in by_name['temperature'].findall('./boundary_conditions/boundary_condition'):
    bc.find('parameter').text = 'TRM_T4_PlacementTemperature'

# Keep horizontal supports and the bottom vertical support, but release the top
# vertical support so nonzero self-weight creates a real mechanical equilibrium
# problem before and after material birth. This keeps the active domain stable
# and avoids the disconnected/free-body fixture issue previously seen in HM.
disp_bcs = by_name['displacement'].find('./boundary_conditions')
if disp_bcs is None:
    raise RuntimeError('displacement BC block missing')
removed = 0
for bc in list(disp_bcs.findall('boundary_condition')):
    geometry = (bc.findtext('geometry') or '').strip()
    component = (bc.findtext('component') or '').strip()
    parameter = (bc.findtext('parameter') or '').strip()
    if parameter != 'dirichlet0':
        raise RuntimeError('unexpected nonzero displacement support in T4 fixture')
    if geometry == 'top' and component == '1':
        disp_bcs.remove(bc)
        removed += 1
if removed != 1:
    raise RuntimeError(f'expected exactly one top-y support to remove, got {removed}')

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
mkdir -p trm-t4-out
set +e
"$OGS_BIN" -o trm-t4-out trm-t4-case/flow_fully_saturated.prj > trm-t4.log 2>&1
rc=$?
set -e
cat trm-t4.log
if [ "$rc" -ne 0 ]; then
  echo "TRM-T4 loaded coupled birth equilibrium E2E failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' trm-t4.log

python3 - <<'PY'
from pathlib import Path
import math
import re
import xml.etree.ElementTree as ET

log = Path('trm-t4.log').read_text(errors='replace')
project = ET.parse('trm-t4-case/flow_fully_saturated.prj').getroot()
if (project.findtext('./processes/process/specific_body_force') or '').strip() != '0 -9.81':
    raise RuntimeError('loaded T4 body force was not retained')

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

# Authoritative loaded-equilibrium evidence: at the birth step the full
# operator must generate a finite mechanical correction and the nonlinear solve
# must drive the subsequent correction to numerical convergence. Components 2
# and 3 are the two displacement components in this monolithic TRM fixture.
start = log.find('Time step #2 started.')
if start < 0:
    raise RuntimeError('birth time step #2 not found')
end = log.find('Time step #2 took', start)
if end < 0:
    raise RuntimeError('completed birth time step #2 not found')
section = log[start:end]
iterations = [int(x) for x in re.findall(r'Iteration #(\d+) started', section)]
if len(iterations) < 2:
    raise RuntimeError(f'expected equilibrium correction iterations at birth, got {iterations}')
conv = re.findall(
    r'Convergence criterion, component ([23]): \|dx\|=([0-9.eE+-]+)', section)
if len(conv) < 4:
    raise RuntimeError('insufficient mechanical convergence evidence at birth')
by_iteration = []
current = []
for line in section.splitlines():
    if 'Iteration #' in line and 'started' in line:
        if current:
            by_iteration.append(current)
            current = []
    m = re.search(r'Convergence criterion, component ([23]): \|dx\|=([0-9.eE+-]+)', line)
    if m:
        current.append(float(m.group(2)))
if current:
    by_iteration.append(current)
by_iteration = [x for x in by_iteration if x]
if len(by_iteration) < 2:
    raise RuntimeError(f'could not group mechanical corrections: {by_iteration}')
first_mech = max(by_iteration[0])
last_mech = max(by_iteration[-1])
if not first_mech > 1e-12:
    raise RuntimeError(f'loaded birth did not create measurable disequilibrium: {first_mech}')
if not last_mech < first_mech * 1e-6:
    raise RuntimeError(
        f'global equilibrium was not restored sufficiently: first={first_mech}, last={last_mech}')
if 'MFront: integration failed' in log:
    raise RuntimeError('MFront integration failure during TRM-T4')

Path('../trm-t4-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=TRM_T4_loaded_coupled_birth_equilibrium\n'
    f'fresh_birth_elements={fresh_unique}\n'
    f'placement_elements={placement_unique}\n'
    'mechanical_birth_reference=current_deformed_configuration\n'
    'birth_stress=zero\n'
    'p_L0=12345\n'
    'T0=310.15\n'
    'specific_body_force=0,-9.81\n'
    'solid_density=2000\n'
    'full_physical_operator=true\n'
    'stiffness_scaling=false\n'
    'residual_homotopy=false\n'
    f'birth_mechanical_first_correction={first_mech:.17g}\n'
    f'birth_mechanical_final_correction={last_mech:.17g}\n'
    f'birth_newton_iterations={len(by_iteration)}\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
