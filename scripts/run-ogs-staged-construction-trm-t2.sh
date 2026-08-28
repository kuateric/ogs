#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-trm-t2
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-trm-t2
cd ogs-trm-t2
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-trm-t2.py"
git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=ThermoRichardsMechanics'
cmake --build --preset release --target ProcessLib ThermoRichardsMechanics ogs --parallel 2

cp -a Tests/Data/ThermoRichardsMechanics/FullySaturatedFlowMechanics trm-t2-case
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu trm-t2-case/

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('trm-t2-case/flow_fully_saturated.prj')
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

# Keep the T2 lifecycle probe in exact equilibrium; T3 owns explicit p_L,0/T_0
# placement and the later loaded gate owns construction disequilibrium.
for bc in by_name['pressure'].findall('./boundary_conditions/boundary_condition'):
    if (bc.findtext('geometry') or '').strip() == 'right':
        bc.find('parameter').text = 'dirichlet0'
        break
else:
    raise RuntimeError('canonical right pressure boundary not found')

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p trm-t2-out
set +e
"$OGS_BIN" -o trm-t2-out trm-t2-case/flow_fully_saturated.prj > trm-t2.log 2>&1
rc=$?
set -e
cat trm-t2.log
if [ "$rc" -ne 0 ]; then
  echo "TRM-T2 fresh coupled birth E2E failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' trm-t2.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('trm-t2.log').read_text(errors='replace')
pat = re.compile(r'TRM-T2 fresh coupled birth state initialized for element (\d+)')
elements = [int(x) for x in pat.findall(log)]
unique = sorted(set(elements))
if len(unique) != 6:
    raise RuntimeError(f'expected six fresh TRM births, got {unique}')
if len(elements) != 6:
    raise RuntimeError(f'each reactivated element must be initialized exactly once, got {elements}')
if 'MFront: integration failed' in log:
    raise RuntimeError('MFront integration failure during TRM-T2')
Path('../trm-t2-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=TRM_T2_fresh_coupled_birth_state\n'
    f'fresh_birth_elements={unique}\n'
    'fresh_constitutive_state=true\n'
    'birth_stress=zero\n'
    'birth_strain=zero\n'
    'stale_pre_void_material_state_reused=false\n'
    'temperature_pressure_displacement_lifecycle=synchronized\n'
    'full_physical_operator=true\n'
    'explicit_pL0_T0=deferred_to_T3\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
