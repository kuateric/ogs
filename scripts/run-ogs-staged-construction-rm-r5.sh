#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

cd "$(dirname "$0")/.."
ROOT="$PWD"
rm -rf ogs-rm-r5 rm-r5-contract.txt rm-r5-evidence.txt

git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-rm-r5
cd ogs-rm-r5
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# Reuse only the already-proven lifecycle/fresh-birth/rebind stack.
python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-rm-r2b-fresh-birth-runtime.py"
python3 "$ROOT/scripts/ogs-staged-construction-rm-r4-material-reassignment.py"
git diff --check

# Canonical-source hardening: the B behaviour must be a different MFront
# behaviour and must carry an additional internal state variable.
grep -q '@Behaviour StandardElasticityBrick;' MaterialLib/SolidModels/MFront/StandardElasticityBrick.mfront
grep -q '@Behaviour MohrCoulombAbboSloan;' MaterialLib/SolidModels/MFront/MohrCoulombAbboSloan.mfront
grep -q '@StateVariable real lam;' MaterialLib/SolidModels/MFront/MohrCoulombAbboSloan.mfront
grep -q 'EquivalentPlasticStrain' MaterialLib/SolidModels/MFront/MohrCoulombAbboSloan.mfront

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON \
  -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=RichardsMechanics'
cmake --build --preset release --target ProcessLib RichardsMechanics ogs --parallel 2

cp -a Tests/Data/RichardsMechanics rm-r5-case
python3 - <<'PY'
from pathlib import Path
from copy import deepcopy
import xml.etree.ElementTree as ET

p = Path('rm-r5-case/A2.prj')
tree = ET.parse(p)
root = tree.getroot()
process = root.find('./processes/process')
crs = process.findall('constitutive_relation')
if len(crs) != 1 or (crs[0].get('id') or '').strip() != '0,1':
    raise RuntimeError('unexpected canonical A2 constitutive relation layout')

base = crs[0]
idx = list(process).index(base)
process.remove(base)

def mfront_relation(material_id, behaviour, properties):
    cr = ET.Element('constitutive_relation', {'id': str(material_id)})
    ET.SubElement(cr, 'type').text = 'MFront'
    ET.SubElement(cr, 'behaviour').text = behaviour
    props = ET.SubElement(cr, 'material_properties')
    for name, parameter in properties:
        ET.SubElement(props, 'material_property', {'name': name, 'parameter': parameter})
    return cr

# Material 1 = RM_A: genuinely different elastic MFront behaviour.
cr_a = mfront_relation(1, 'StandardElasticityBrick', [
    ('YoungModulus', 'E_A'),
    ('PoissonRatio', 'nu'),
])
# Material 0 = RM_B: Mohr-Coulomb has the additional MGIS state variable lam /
# EquivalentPlasticStrain. High cohesion keeps this lifecycle-hardening case
# away from a plastic-limit-point blocker; R5 tests cross-behaviour state
# ownership, not plastic collapse.
cr_b = mfront_relation(0, 'MohrCoulombAbboSloan', [
    ('YoungModulus', 'E_B'),
    ('PoissonRatio', 'nu'),
    ('Cohesion', 'MC_Cohesion'),
    ('FrictionAngle', 'MC_FrictionAngle'),
    ('DilatancyAngle', 'MC_DilatancyAngle'),
    ('TransitionAngle', 'MC_TransitionAngle'),
    ('TensionCutOffParameter', 'MC_TensionCutOff'),
])
process.insert(idx, cr_a)
process.insert(idx + 1, cr_b)

params = root.find('./parameters')
def add_scalar(name, value):
    par = ET.SubElement(params, 'parameter')
    ET.SubElement(par, 'name').text = name
    ET.SubElement(par, 'type').text = 'Constant'
    ET.SubElement(par, 'value').text = str(value)

# Preserve canonical E=4e9 as RM_A and use a different RM_B stiffness.
ep = next((x for x in params.findall('parameter') if x.findtext('name') == 'E'), None)
if ep is None or float(ep.findtext('value')) != 4e9:
    raise RuntimeError('canonical A2 E changed')
add_scalar('E_A', '4.0e9')
add_scalar('E_B', '2.0e9')
add_scalar('MC_Cohesion', '1.0e12')
add_scalar('MC_FrictionAngle', '25')
add_scalar('MC_DilatancyAngle', '10')
add_scalar('MC_TransitionAngle', '27')
add_scalar('MC_TensionCutOff', '1.0e12')

variables = {pv.findtext('name').strip(): pv for pv in root.findall('./process_variables/process_variable')}
for name in ('pressure', 'displacement'):
    pv = variables[name]
    ds = pv.find('deactivated_subdomains/deactivated_subdomain')
    if ds is None or (ds.findtext('material_ids') or '').strip() != '1':
        raise RuntimeError(f'missing synchronized RM lifecycle for {name}')
    for tag in ('time_curve', 'line_segment', 'boundary_parameter'):
        x = ds.find(tag)
        if x is not None:
            ds.remove(x)
    ti = ET.Element('time_interval')
    ET.SubElement(ti, 'start').text = '2160'
    ET.SubElement(ti, 'end').text = '4320'
    ds.insert(0, ti)
    am = ET.Element('activation_material_id')
    am.text = '0'
    mat = ds.find('material_ids')
    ds.insert(list(ds).index(mat) + 1, am)

load_top = next((x for x in params.findall('parameter') if x.findtext('name') == 'load_top'), None)
if load_top is None or float(load_top.findtext('values')) != -12e6:
    raise RuntimeError('canonical A2 top load changed')

ts = root.find('./time_loop/processes/process/time_stepping')
for child in list(ts):
    if child.tag in {'t_end', 'timesteps'}:
        ts.remove(child)
ET.SubElement(ts, 't_end').text = '4334'
steps = ET.SubElement(ts, 'timesteps')
for dt in ('0.01', '2159.99', '2160', '14'):
    pair = ET.SubElement(steps, 'pair')
    ET.SubElement(pair, 'repeat').text = '1'
    ET.SubElement(pair, 'delta_t').text = dt

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
Path('../rm-r5-contract.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=RM_R5_MFront_MGIS_cross_behaviour\n'
    'RM_A_material_id=1\nbehaviour_A=StandardElasticityBrick\n'
    'void_interval_start=2160\nvoid_interval_end=4320\n'
    'RM_B_material_id=0\nbehaviour_B=MohrCoulombAbboSloan\n'
    'behaviour_B_state=EquivalentPlasticStrain\n'
    'cross_behaviour=true\nfresh_MFront_state_required=true\n'
    'stress_free_birth=true\nexplicit_p_L0=true\n'
    'full_physical_operator=true\n'
    'stiffness_scaling=false\nresidual_homotopy=false\nmaterial_homotopy=false\n'
)
PY

# Assert the executed input itself contains two different MFront behaviours.
grep -q '<behaviour>StandardElasticityBrick</behaviour>' rm-r5-case/A2.prj
grep -q '<behaviour>MohrCoulombAbboSloan</behaviour>' rm-r5-case/A2.prj

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p rm-r5-out
"$OGS_BIN" -o rm-r5-out rm-r5-case/A2.prj > rm-r5.log 2>&1
cat rm-r5.log

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' rm-r5.log
grep -Eq 'RM-R4 activation material reassigned.*old_material_id=1, new_material_id=0' rm-r5.log
grep -Eq 'RM-R4 constitutive material rebound.*old_material_id=1, new_material_id=0' rm-r5.log
grep -q 'RM fresh-birth state initialized' rm-r5.log
grep -q 'RM birth reference captured' rm-r5.log
! grep -q 'MFront: integration failed' rm-r5.log
! grep -Eqi 'stiffness[_ -]?scale|residual[_ -]?homotopy|material[_ -]?homotopy' rm-r5.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('rm-r5.log').read_text(errors='replace')
reb = re.search(r'RM-R4 constitutive material rebound for element (\d+): old_material_id=(\d+), new_material_id=(\d+)', log)
if reb is None or tuple(map(int, reb.groups()[1:])) != (1, 0):
    raise RuntimeError('missing authoritative A->B constitutive rebind evidence')
birth = re.search(r'RM fresh-birth event published.*?at t=([-+0-9.eE]+)', log)
if birth is None or abs(float(birth.group(1)) - 4334.0) > 1e-9:
    raise RuntimeError(f'unexpected cross-behaviour birth time: {birth.group(1) if birth else None}')
summary = re.search(r'The whole computation of the time stepping took (\d+) steps, in which\s+the accepted steps are (\d+), and the rejected steps are (\d+)', log)
if not summary:
    raise RuntimeError('missing physical time-step summary')
total, accepted, rejected = map(int, summary.groups())
if (total, accepted, rejected) != (4, 4, 0):
    raise RuntimeError(f'unexpected R5 time stepping: {(total, accepted, rejected)}')
Path('../rm-r5-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=RM_R5_MFront_MGIS_cross_behaviour\n'
    f'element_id={reb.group(1)}\nold_material_id=1\nnew_material_id=0\n'
    'behaviour_A=StandardElasticityBrick\n'
    'behaviour_B=MohrCoulombAbboSloan\n'
    'behaviour_B_state=EquivalentPlasticStrain\n'
    'cross_behaviour=true\nconstitutive_rebind=true\nfresh_MFront_state=true\n'
    'MFront_integration_failed=false\n'
    'stress_free_birth=true\nexplicit_p_L0=true\nfull_physical_operator=true\n'
    'stiffness_scaling=false\nresidual_homotopy=false\nmaterial_homotopy=false\n'
    'activation_time=4334\nphysical_time_steps=4\nrejected_steps=0\nruntime_exit=0\n'
)
PY
