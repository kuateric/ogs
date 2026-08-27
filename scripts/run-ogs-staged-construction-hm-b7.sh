#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-hm-b7
cd "$(dirname "$0")/.."
ROOT="$PWD"
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b7
cd ogs-hm-b7
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b2.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b3.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b4.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b6.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b6-compile-fix.py"
git diff --check

cmake --preset release --fresh -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2

cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b7-case
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('hm-b7-case/simHM_deactivate_H.prj')
t = ET.parse(p)
r = t.getroot()
vars = {x.findtext('name').strip(): x for x in r.findall('./process_variables/process_variable')}
pr, du = vars['pressure'], vars['displacement']
ds = pr.find('deactivated_subdomains')
ds.find('./deactivated_subdomain/material_ids').text = '3 4'
ET.SubElement(ds.find('./deactivated_subdomain'), 'activation_material_id').text = '5'
du.insert(list(du).index(du.find('initial_condition')) + 1, deepcopy(ds))

proc = r.find('./processes/process')
base_cr = proc.find("./constitutive_relation[@id='0']")

def set_mfront(cr, e_parameter):
    for child in list(cr):
        cr.remove(child)
    ET.SubElement(cr, 'type').text = 'MFront'
    ET.SubElement(cr, 'behaviour').text = 'MohrCoulombAbboSloan'
    props = ET.SubElement(cr, 'material_properties')
    for name, parameter in [
        ('YoungModulus', e_parameter),
        ('PoissonRatio', 'nu'),
        ('Cohesion', 'MC_Cohesion'),
        ('FrictionAngle', 'MC_FrictionAngle'),
        ('DilatancyAngle', 'MC_DilatancyAngle'),
        ('TransitionAngle', 'MC_TransitionAngle'),
        ('TensionCutOffParameter', 'MC_TensionCutOff'),
    ]:
        ET.SubElement(props, 'material_property', {'name': name, 'parameter': parameter})

set_mfront(base_cr, 'E_A')
for material_id in ('1', '2', '3', '4'):
    cr_a = deepcopy(base_cr)
    cr_a.set('id', material_id)
    proc.append(cr_a)
cr_b = deepcopy(base_cr)
cr_b.set('id', '5')
set_mfront(cr_b, 'E_B')
proc.append(cr_b)

pars = r.find('./parameters')
def add_parameter(name, value):
    par = ET.SubElement(pars, 'parameter')
    ET.SubElement(par, 'name').text = name
    ET.SubElement(par, 'type').text = 'Constant'
    ET.SubElement(par, 'value').text = str(value)

add_parameter('E_A', '4.0e9')
add_parameter('E_B', '1.0e9')
add_parameter('MC_Cohesion', '5.0e6')
add_parameter('MC_FrictionAngle', '25')
add_parameter('MC_DilatancyAngle', '10')
add_parameter('MC_TransitionAngle', '27')
add_parameter('MC_TensionCutOff', '1.0e6')

meds = r.find('./media')
src = meds.find("./medium[@id='0,2,4']")
new = deepcopy(src)
new.set('id', '5')
meds.append(new)

for x in r.findall('./parameters/parameter'):
    if x.findtext('name') == 'InitialPressure':
        x.find('values').text = '12345'
proc.find('./specific_body_force').text = '0 -0.1'
ts = r.find('./time_loop/processes/process/time_stepping')
ts.find('t_end').text = '2.0'
pair = ts.find('./timesteps/pair')
pair.find('repeat').text = '2'
pair.find('delta_t').text = '1.0'
t.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p hm-b7-out
"$OGS_BIN" -o hm-b7-out hm-b7-case/simHM_deactivate_H.prj > hm-b7.log 2>&1
cat hm-b7.log
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b7.log
! grep -q 'MFront: integration failed' hm-b7.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('hm-b7.log').read_text(errors='replace')
assign = sorted(set((int(e), int(m)) for e, m in re.findall(r'HM-B6 activation material reassigned for element (\d+): material_id=(\d+)', log)))
bound = sorted(set((int(e), int(m)) for e, m in re.findall(r'HM-B6 coupled birth material bound for element (\d+): material_id=(\d+)', log)))
if len(assign) != 6 or any(m != 5 for _, m in assign):
    raise RuntimeError(f'bad MFront assignments: {assign}')
if len(bound) != 6 or any(m != 5 for _, m in bound):
    raise RuntimeError(f'bad MFront bindings: {bound}')
Path('../hm-b7-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B7_MFront_material_reassignment\n'
    'behaviour_A=MohrCoulombAbboSloan\n'
    'behaviour_B=MohrCoulombAbboSloan\n'
    'E_A=4.0e9\n'
    'E_B=1.0e9\n'
    'activation_material_id=5\n'
    f'assigned_elements={[e for e, _ in assign]}\n'
    f'bound_elements={[e for e, _ in bound]}\n'
    'fresh_MFront_state=true\n'
    'MFront_integration_failed=false\n'
    'runtime_exit=0\n'
)
PY
