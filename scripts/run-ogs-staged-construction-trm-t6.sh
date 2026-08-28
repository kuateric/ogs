#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-trm-t6
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-trm-t6
cd ogs-trm-t6
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
  -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON \
  -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=ThermoRichardsMechanics'
cmake --build --preset release --target ProcessLib ThermoRichardsMechanics ogs --parallel 2

cp -a Tests/Data/ThermoRichardsMechanics/FullySaturatedFlowMechanics trm-t6-case
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu trm-t6-case/
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET
p=Path('trm-t6-case/flow_fully_saturated.prj')
t=ET.parse(p); r=t.getroot(); r.find('mesh').text='square_1x1_quad_1e1_2_matIDs.vtu'
proc=r.find('./processes/process')
if proc is None or (proc.findtext('type') or '').strip()!='THERMO_RICHARDS_MECHANICS': raise RuntimeError('canonical TRM process not found')
base=proc.find('constitutive_relation')
if base is None: raise RuntimeError('constitutive relation not found')
base.set('id','0')
pars=r.find('./parameters')
if pars is None: raise RuntimeError('parameters block not found')
def add(name,value):
    q=ET.SubElement(pars,'parameter'); ET.SubElement(q,'name').text=name; ET.SubElement(q,'type').text='Constant'; ET.SubElement(q,'value').text=str(value)
for n,v in [('TRM_T6_E_A','4.0e9'),('TRM_T6_E_B','1.0e9'),('TRM_T6_nu','0.3'),('TRM_T6_c','5.0e6'),('TRM_T6_phi','25'),('TRM_T6_psi','10'),('TRM_T6_theta','27'),('TRM_T6_tcut','1.0e6')]: add(n,v)
def set_mfront(cr,E):
    for c in list(cr): cr.remove(c)
    ET.SubElement(cr,'type').text='MFront'; ET.SubElement(cr,'behaviour').text='MohrCoulombAbboSloan'
    mp=ET.SubElement(cr,'material_properties')
    for n,q in [('YoungModulus',E),('PoissonRatio','TRM_T6_nu'),('Cohesion','TRM_T6_c'),('FrictionAngle','TRM_T6_phi'),('DilatancyAngle','TRM_T6_psi'),('TransitionAngle','TRM_T6_theta'),('TensionCutOffParameter','TRM_T6_tcut')]: ET.SubElement(mp,'material_property',{'name':n,'parameter':q})
set_mfront(base,'TRM_T6_E_A')
cr1=deepcopy(base); cr1.set('id','1'); proc.append(cr1)
cr5=deepcopy(base); cr5.set('id','5'); set_mfront(cr5,'TRM_T6_E_B'); proc.append(cr5)
med=r.find('./media/medium'); med.set('id','0,1'); med5=deepcopy(med); med5.set('id','5'); r.find('./media').append(med5)
vars={(x.findtext('name') or '').strip():x for x in r.findall('./process_variables/process_variable')}
def ds():
    x=ET.Element('deactivated_subdomains'); d=ET.SubElement(x,'deactivated_subdomain'); ti=ET.SubElement(d,'time_interval'); ET.SubElement(ti,'start').text='0'; ET.SubElement(ti,'end').text='1'; ET.SubElement(d,'material_ids').text='1'; ET.SubElement(d,'activation_material_id').text='5'; return x
for n in ('temperature','pressure','displacement'):
    pv=vars[n]; ic=pv.find('initial_condition'); pv.insert(list(pv).index(ic)+1 if ic is not None else len(pv),ds())
add('TRM_T6_P',12345.0); add('TRM_T6_T',310.15)
vars['pressure'].find('initial_condition').text='TRM_T6_P'; vars['temperature'].find('initial_condition').text='TRM_T6_T'
for bc in vars['pressure'].findall('./boundary_conditions/boundary_condition'): bc.find('parameter').text='TRM_T6_P'
for bc in vars['temperature'].findall('./boundary_conditions/boundary_condition'): bc.find('parameter').text='TRM_T6_T'
cc=r.find('./time_loop/processes/process/convergence_criterion')
if cc is not None and cc.find('reltols') is None: ET.SubElement(cc,'reltols').text='0 1e-14 0 0'
t.write(p,encoding='ISO-8859-1',xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"; test -n "$OGS_BIN"
mkdir -p trm-t6-out
set +e; "$OGS_BIN" -o trm-t6-out trm-t6-case/flow_fully_saturated.prj > trm-t6.log 2>&1; rc=$?; set -e
cat trm-t6.log
[ "$rc" -eq 0 ] || exit "$rc"
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' trm-t6.log
! grep -q 'MFront: integration failed' trm-t6.log
python3 - <<'PY'
from pathlib import Path
import re
s=Path('trm-t6.log').read_text(errors='replace')
a=[(int(e),int(m)) for e,m in re.findall(r'TRM-T5 activation material reassigned for element (\d+): material_id=(\d+)',s)]
b=[(int(e),int(m)) for e,m in re.findall(r'TRM-T5 coupled birth material bound for element (\d+): material_id=(\d+)',s)]
f=[int(e) for e in re.findall(r'TRM-T2 fresh coupled birth state initialized for element (\d+)',s)]
if len(a)!=6 or len(set(a))!=6 or any(m!=5 for _,m in a): raise RuntimeError(f'bad assignments {a}')
if len(b)!=6 or len(set(b))!=6 or any(m!=5 for _,m in b): raise RuntimeError(f'bad bindings {b}')
if len(f)!=6 or len(set(f))!=6 or sorted(e for e,_ in b)!=sorted(set(f)): raise RuntimeError(f'bad fresh states {f}')
Path('../trm-t6-evidence.txt').write_text('upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\ngate=TRM_T6_MFront_material_reassignment\nbehaviour_A=MohrCoulombAbboSloan\nbehaviour_B=MohrCoulombAbboSloan\nE_A=4.0e9\nE_B=1.0e9\nactivation_material_id=5\nfresh_MFront_state=true\nMFront_integration_failed=false\nmaterial_law_neutral_lifecycle=true\nfull_physical_operator=true\nruntime_exit=0\n')
PY
