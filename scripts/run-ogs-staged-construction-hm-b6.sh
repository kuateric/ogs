#!/usr/bin/env bash
set -euo pipefail
OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"
rm -rf ogs-hm-b6
cd "$(dirname "$0")/.."
ROOT="$PWD"
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b6
cd ogs-hm-b6
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b2.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b3.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b4.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b6.py"
git diff --check
cmake --preset release --fresh -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2
cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b6-case
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET
p=Path('hm-b6-case/simHM_deactivate_H.prj')
t=ET.parse(p); r=t.getroot()
vars={x.findtext('name').strip():x for x in r.findall('./process_variables/process_variable')}
pr,du=vars['pressure'],vars['displacement']
ds=pr.find('deactivated_subdomains')
mid=ds.find('./deactivated_subdomain/material_ids'); mid.text='3 4'
ET.SubElement(ds.find('./deactivated_subdomain'),'activation_material_id').text='5'
du.insert(list(du).index(du.find('initial_condition'))+1,deepcopy(ds))
# second constitutive relation for newborn backfill
proc=r.find('./processes/process')
cr=ET.SubElement(proc,'constitutive_relation',{'id':'5'})
ET.SubElement(cr,'type').text='LinearElasticIsotropic'
ET.SubElement(cr,'youngs_modulus').text='E_B'
ET.SubElement(cr,'poissons_ratio').text='nu'
pars=r.find('./parameters')
par=ET.SubElement(pars,'parameter'); ET.SubElement(par,'name').text='E_B'; ET.SubElement(par,'type').text='Constant'; ET.SubElement(par,'value').text='2.5e7'
# medium for target id 5 cloned from host medium
meds=r.find('./media'); src=meds.find("./medium[@id='0,2,4']"); new=deepcopy(src); new.set('id','5'); meds.append(new)
# placement pressure and connected loaded domain
for x in r.findall('./parameters/parameter'):
    if x.findtext('name')=='InitialPressure': x.find('values').text='12345'
body=r.find('./processes/process/specific_body_force'); body.text='0 -0.1'
ts=r.find('./time_loop/processes/process/time_stepping'); ts.find('t_end').text='2.0'; pair=ts.find('./timesteps/pair'); pair.find('repeat').text='2'; pair.find('delta_t').text='1.0'
t.write(p,encoding='ISO-8859-1',xml_declaration=True)
PY
OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p hm-b6-out
"$OGS_BIN" -o hm-b6-out hm-b6-case/simHM_deactivate_H.prj > hm-b6.log 2>&1
cat hm-b6.log
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b6.log
python3 - <<'PY'
from pathlib import Path
import re
log=Path('hm-b6.log').read_text(errors='replace')
assign=sorted(set((int(e),int(m)) for e,m in re.findall(r'HM-B6 activation material reassigned for element (\d+): material_id=(\d+)',log)))
bound=sorted(set((int(e),int(m)) for e,m in re.findall(r'HM-B6 coupled birth material bound for element (\d+): material_id=(\d+)',log)))
if len(assign)!=6 or any(m!=5 for _,m in assign): raise RuntimeError(f'bad assignments: {assign}')
if len(bound)!=6 or any(m!=5 for _,m in bound): raise RuntimeError(f'bad bindings: {bound}')
Path('../hm-b6-evidence.txt').write_text('upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\ngate=HM_B6_material_reassignment\nactivation_material_id=5\nE_A=1e8\nE_B=2.5e7\nassigned_elements='+str([e for e,_ in assign])+'\nbound_elements='+str([e for e,_ in bound])+'\nfresh_state_from_new_material=true\nruntime_exit=0\n')
PY
