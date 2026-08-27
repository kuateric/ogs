#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-trm-t1b
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-trm-t1b
cd ogs-trm-t1b
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# T1A already proves that the canonical monolithic TRM process routes assembly,
# postTimestep state commit, and secondary-variable evaluation through one
# process-wide active-element set.  T1B therefore tests the runtime lifecycle
# itself without changing production semantics: temperature, pressure, and
# displacement receive the same staged-construction restriction.  Under the
# existing Process union semantics, identical restrictions remain identical;
# no HM-B2-style Process patch is required for a synchronized TRM void.

# Instrument the real TRM local assembler.  If an element is absent from this
# trace, none of its monolithic thermal/Richards/mechanical local contributions
# can enter the global assembly at that time.
python3 - <<'PY'
from pathlib import Path
p = Path('ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM-impl.h')
text = p.read_text(encoding='utf-8')
anchor = '''    assembleWithJacobian(double const t, double const dt,
                         std::vector<double> const& local_x,
                         std::vector<double> const& local_x_prev,
                         std::vector<double>& local_rhs_data,
                         std::vector<double>& local_Jac_data)
{
    auto& medium =
'''
replacement = '''    assembleWithJacobian(double const t, double const dt,
                         std::vector<double> const& local_x,
                         std::vector<double> const& local_x_prev,
                         std::vector<double>& local_rhs_data,
                         std::vector<double>& local_Jac_data)
{
    INFO("TRM-T1B coupled assembly element {:d} at t = {:g}",
         this->element_.getID(), t);
    auto& medium =
'''
if text.count(anchor) != 1:
    raise RuntimeError('unexpected TRM assembleWithJacobian entry')
p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
PY

git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=ThermoRichardsMechanics'
cmake --build --preset release --target ProcessLib ThermoRichardsMechanics ogs --parallel 2

# Start from the small canonical fully-saturated TRM fixture, but use the
# canonical 12-cell two-material TRM mesh so that one connected material cluster
# can be removed while the other remains active.
cp -a Tests/Data/ThermoRichardsMechanics/FullySaturatedFlowMechanics trm-t1b-case
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu \
   trm-t1b-case/

python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('trm-t1b-case/flow_fully_saturated.prj')
tree = ET.parse(p)
root = tree.getroot()

mesh = root.find('mesh')
if mesh is None:
    raise RuntimeError('canonical TRM mesh entry not found')
mesh.text = 'square_1x1_quad_1e1_2_matIDs.vtu'

# The replacement mesh contains MaterialIDs 0 and 1.  The canonical constitutive
# relation remains material-law neutral and common to both; only the medium map
# needs to declare that both IDs use the same fully-saturated medium.
medium = root.find('./media/medium')
if medium is None:
    raise RuntimeError('canonical TRM medium not found')
medium.set('id', '0,1')

variables = root.findall('./process_variables/process_variable')
by_name = {}
for pv in variables:
    name = pv.findtext('name')
    if name:
        by_name[name.strip()] = pv
required = ('temperature', 'pressure', 'displacement')
if any(name not in by_name for name in required):
    raise RuntimeError(f'unexpected TRM variables: {sorted(by_name)}')

# The material-1 cluster is a true monolithic void over the first physical
# interval.  Every primary variable receives the identical declaration, which
# also activates OGS' existing DeactivatedSubdomainDirichlet treatment for the
# corresponding inactive DOFs.
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
        raise RuntimeError(f'{name} unexpectedly already has deactivated_subdomains')
    ic = pv.find('initial_condition')
    insert_at = list(pv).index(ic) + 1 if ic is not None else len(pv)
    pv.insert(insert_at, make_deactivation())

# T1B isolates lifecycle algebra from loaded construction equilibrium.  Keep the
# canonical zero body force, uniform temperature, and make the pressure field
# gradient-free so the zero-displacement state remains an exact equilibrium in
# both active-domain configurations.  Loaded equilibrium restoration belongs to
# the later TRM gate after fresh thermal birth and placement-state semantics.
right_pressure_bc = None
for bc in by_name['pressure'].findall('./boundary_conditions/boundary_condition'):
    if (bc.findtext('geometry') or '').strip() == 'right':
        right_pressure_bc = bc
        break
if right_pressure_bc is None:
    raise RuntimeError('canonical right pressure boundary not found')
param = right_pressure_bc.find('parameter')
if param is None:
    raise RuntimeError('canonical right pressure boundary parameter not found')
param.text = 'dirichlet0'

# The canonical case already runs t=0 -> 1 -> 2.  t=1 is the inactive snapshot,
# t=2 is the reactivated snapshot.
ts = root.find('./time_loop/processes/process/time_stepping')
if ts is None or ts.findtext('t_end') != '2':
    raise RuntimeError('unexpected canonical TRM time horizon')

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p trm-t1b-out
set +e
"$OGS_BIN" -o trm-t1b-out trm-t1b-case/flow_fully_saturated.prj > trm-t1b.log 2>&1
rc=$?
set -e
cat trm-t1b.log
if [ "$rc" -ne 0 ]; then
  echo "TRM-T1B synchronized coupled runtime probe failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' trm-t1b.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('trm-t1b.log').read_text(errors='replace')
pat = re.compile(r'TRM-T1B coupled assembly element (\d+) at t = ([-+0-9.eE]+)')
records = [(int(e), float(t)) for e, t in pat.findall(log)]
if not records:
    raise RuntimeError('no TRM-T1B coupled assembly evidence found')
by_time = {}
for e, t in records:
    by_time.setdefault(round(t, 12), set()).add(e)
active_t1 = by_time.get(1.0, set())
active_t2 = by_time.get(2.0, set())
if not active_t1 or not active_t2:
    raise RuntimeError(
        f'missing TRM-T1B assembly snapshots: t1={len(active_t1)} t2={len(active_t2)}')
if len(active_t2) != 12:
    raise RuntimeError(f'expected all 12 TRM elements after reactivation, got {sorted(active_t2)}')
if len(active_t1) != 6:
    raise RuntimeError(f'expected exactly 6 active TRM elements during void, got {sorted(active_t1)}')
if not active_t1 < active_t2:
    raise RuntimeError(
        f'TRM domain did not shrink/reactivate: t1={sorted(active_t1)}, t2={sorted(active_t2)}')
reactivated = active_t2 - active_t1
if len(reactivated) != 6:
    raise RuntimeError(f'expected 6 reactivated elements, got {sorted(reactivated)}')

Path('../trm-t1b-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=TRM_T1B_synchronized_coupled_runtime_deactivation\n'
    f'active_elements_t1={sorted(active_t1)}\n'
    f'active_elements_t2={sorted(active_t2)}\n'
    f'reactivated_elements={sorted(reactivated)}\n'
    'temperature_pressure_displacement_lifecycle=synchronized\n'
    'monolithic_TRM_local_assembly_routed_by_active_set=true\n'
    'production_process_patch=none\n'
    'body_force_for_lifecycle_gate=0\n'
    'pressure_gradient_for_lifecycle_gate=0\n'
    'physical_time_horizon=2.0\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
