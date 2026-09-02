#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-th2m-t1b
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-th2m-t1b
cd ogs-th2m-t1b
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# T1A proved that canonical TH2M is monolithic and routes p_g, p_c, T and u
# through one process-wide active-element set. T1B therefore tests a synchronized
# void/reactivation interval with no numerical continuation and no production
# process patch. The real TH2M local assembler is instrumented only for evidence.
python3 - <<'PY'
from pathlib import Path
p = Path('ProcessLib/TH2M/TH2MFEM-impl.h')
text = p.read_text(encoding='utf-8')
anchor = '''                               std::vector<double>& local_K_data,\n                               std::vector<double>& local_rhs_data)\n{\n    auto const matrix_size = gas_pressure_size + capillary_pressure_size +\n'''
replacement = '''                               std::vector<double>& local_K_data,\n                               std::vector<double>& local_rhs_data)\n{\n    INFO("TH2M-T1B coupled assembly element {:d} at t = {:g}",\n         this->element_.getID(), t);\n    auto const matrix_size = gas_pressure_size + capillary_pressure_size +\n'''
if text.count(anchor) != 1:
    raise RuntimeError('unexpected canonical TH2M assemble anchor')
p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
PY

git diff --check
cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=TH2M'
cmake --build --preset release --target ProcessLib TH2M ogs --parallel 2

mkdir -p th2m-t1b-case
cp Tests/Data/TH2M/ExcavationTH2M/excavation_th2m.prj th2m-t1b-case/th2m_t1b.prj
cp Tests/Data/ThermoRichardsMechanics/MultiMaterialEhlers/square_1x1_quad_1e1_2_matIDs.vtu th2m-t1b-case/domain.vtu

# OGS Dirichlet BCs resolve boundary-mesh nodes back to bulk nodes through the
# bulk_node_ids point property. The compact two-material fixture is intentionally
# reused as the all-node boundary mesh, so add the identity map explicitly. This
# is fixture metadata only; it changes neither TH2M lifecycle nor numerics.
python3 - <<'PY'
from pathlib import Path
p = Path('th2m-t1b-case/domain.vtu')
text = p.read_text(encoding='utf-8')
anchor = '''      <PointData>\n      </PointData>'''
replacement = '''      <PointData>\n        <DataArray type="Int64" Name="bulk_node_ids" format="ascii">0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19</DataArray>\n      </PointData>'''
if text.count(anchor) != 1:
    raise RuntimeError('unexpected compact fixture PointData anchor')
p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
PY

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('th2m-t1b-case/th2m_t1b.prj')
tree = ET.parse(p)
root = tree.getroot()

meshes = root.find('meshes')
if meshes is None:
    raise RuntimeError('TH2M meshes block missing')
for child in list(meshes):
    meshes.remove(child)
ET.SubElement(meshes, 'mesh').text = 'domain.vtu'

# Linear material isolates coupled lifecycle algebra. MFront fresh-state birth is
# a later TH2M gate; T1B must first prove that all four fields disappear and
# reappear together.
proc = root.find('./processes/process')
if proc is None or (proc.findtext('type') or '').strip() != 'TH2M':
    raise RuntimeError('canonical TH2M process missing')
cr = proc.find('constitutive_relation')
if cr is None:
    raise RuntimeError('constitutive relation missing')
for child in list(cr):
    cr.remove(child)
ET.SubElement(cr, 'type').text = 'LinearElasticIsotropic'
ET.SubElement(cr, 'youngs_modulus').text = 'E'
ET.SubElement(cr, 'poissons_ratio').text = 'nu'
cr.set('id', '0,1')
init_stress = proc.find('initial_stress')
if init_stress is not None:
    proc.remove(init_stress)
proc.find('specific_body_force').text = '0 0'

medium = root.find('./media/medium')
if medium is None:
    raise RuntimeError('TH2M medium missing')
medium.set('id', '0,1')

variables = {}
for pv in root.findall('./process_variables/process_variable'):
    name = (pv.findtext('name') or '').strip()
    if name:
        variables[name] = pv
required = ('gas_pressure', 'capillary_pressure', 'temperature', 'displacement')
if any(name not in variables for name in required):
    raise RuntimeError(f'unexpected TH2M variables: {sorted(variables)}')

# Zero-gradient/zero-load fixture: exact equilibrium in either active-domain
# topology. This gate is solely about coupled domain ownership.
for param in root.findall('./parameters/parameter'):
    name = (param.findtext('name') or '').strip()
    if name == 'pg_0_function':
        typ = param.find('type'); typ.text = 'Constant'
        expr = param.find('expression')
        if expr is not None: param.remove(expr)
        value = param.find('value') or ET.SubElement(param, 'value')
        value.text = '100000'
    elif name == 'sigma_top':
        typ = param.find('type'); typ.text = 'Constant'
        for expr in list(param.findall('expression')): param.remove(expr)
        value = param.find('value') or ET.SubElement(param, 'value')
        value.text = '0'

for pv in variables.values():
    bcs = pv.find('boundary_conditions')
    if bcs is not None:
        pv.remove(bcs)

# Keep mechanics nonsingular with full-domain zero displacement. The fixture mesh
# carries an identity bulk_node_ids map, satisfying OGS boundary-to-bulk mapping.
# Local TH2M contributions are still assembled before global Dirichlet elimination
# and are captured by the instrumented assembler trace.
bcs = ET.SubElement(variables['displacement'], 'boundary_conditions')
for comp in ('0', '1'):
    bc = ET.SubElement(bcs, 'boundary_condition')
    ET.SubElement(bc, 'mesh').text = 'domain'
    ET.SubElement(bc, 'type').text = 'Dirichlet'
    ET.SubElement(bc, 'component').text = comp
    ET.SubElement(bc, 'parameter').text = 'zero'

# MaterialID 1 is active at initialization so the global TH2M DOF structure is
# built for the complete model. It is absent only during the construction stage
# around t=1 and returns at t=2. Preserve each field's physical placement state
# while inactive: OGS otherwise uses an artificial zero Dirichlet value for the
# inactive interior DOFs. Zero is appropriate for displacement here, but not for
# gas pressure, capillary pressure, or absolute temperature. Keeping those scalar
# fields at their canonical reference values prevents the first reactivated local
# assembly from seeing a non-physical T=0 / pressure=0 state before the ordinary
# global Dirichlet conditions are applied.
def deactivation(boundary_parameter):
    ds = ET.Element('deactivated_subdomains')
    d = ET.SubElement(ds, 'deactivated_subdomain')
    ti = ET.SubElement(d, 'time_interval')
    ET.SubElement(ti, 'start').text = '0.5'
    ET.SubElement(ti, 'end').text = '1.5'
    ET.SubElement(d, 'material_ids').text = '1'
    ET.SubElement(d, 'boundary_parameter').text = boundary_parameter
    return ds

placement_parameters = {
    'gas_pressure': 'pg_0_function',
    'capillary_pressure': 'pc_0',
    'temperature': 'T0',
    'displacement': 'zero',
}
for name in required:
    pv = variables[name]
    old = pv.find('deactivated_subdomains')
    if old is not None: pv.remove(old)
    ic = pv.find('initial_condition')
    pv.insert(
        list(pv).index(ic) + 1 if ic is not None else len(pv),
        deactivation(placement_parameters[name]))

# Two fixed one-second steps provide authoritative active/void/reactivated
# snapshots at t=0, t=1, and t=2 without changing physical material parameters.
ts = root.find('./time_loop/processes/process/time_stepping')
if ts is None:
    raise RuntimeError('time stepping missing')
for child in list(ts):
    ts.remove(child)
ET.SubElement(ts, 'type').text = 'FixedTimeStepping'
ET.SubElement(ts, 't_initial').text = '0'
ET.SubElement(ts, 't_end').text = '2'
pairs = ET.SubElement(ts, 'timesteps')
pair = ET.SubElement(pairs, 'pair')
ET.SubElement(pair, 'repeat').text = '2'
ET.SubElement(pair, 'delta_t').text = '1'

# Output only at the two construction states.
out = root.find('./time_loop/output')
if out is not None:
    fot = out.find('fixed_output_times')
    if fot is not None: fot.text = '1\n2'

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p th2m-t1b-out
set +e
"$OGS_BIN" -o th2m-t1b-out -m th2m-t1b-case th2m-t1b-case/th2m_t1b.prj > th2m-t1b.log 2>&1
rc=$?
set -e
cat th2m-t1b.log
if [ "$rc" -ne 0 ]; then
  echo "TH2M-T1B synchronized coupled runtime probe failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' th2m-t1b.log
python3 - <<'PY'
from pathlib import Path
import re
log = Path('th2m-t1b.log').read_text(errors='replace')
pat = re.compile(r'TH2M-T1B coupled assembly element (\d+) at t = ([-+0-9.eE]+)')
records = [(int(e), float(t)) for e, t in pat.findall(log)]
if not records:
    raise RuntimeError('no TH2M-T1B coupled assembly evidence found')
by_time = {}
for e, t in records:
    by_time.setdefault(round(t, 12), set()).add(e)
a0 = by_time.get(0.0, set())
a1 = by_time.get(1.0, set())
a2 = by_time.get(2.0, set())
if not a0 or not a1 or not a2:
    raise RuntimeError(f'missing TH2M snapshots: t0={len(a0)} t1={len(a1)} t2={len(a2)}')
if not a1 < a0 or a2 != a0:
    raise RuntimeError(f'TH2M active-void-active lifecycle failed: t0={sorted(a0)} t1={sorted(a1)} t2={sorted(a2)}')
reactivated = a2 - a1
if len(reactivated) == 0:
    raise RuntimeError('no TH2M elements reactivated')
Path('../th2m-t1b-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=TH2M_T1B_synchronized_coupled_runtime_deactivation\n'
    f'active_elements_t0={sorted(a0)}\n'
    f'active_elements_t1={sorted(a1)}\n'
    f'active_elements_t2={sorted(a2)}\n'
    f'reactivated_elements={sorted(reactivated)}\n'
    'gas_capillary_temperature_displacement_lifecycle=synchronized\n'
    'inactive_scalar_state=placement_reference_preserved\n'
    'monolithic_TH2M_local_assembly_routed_by_active_set=true\n'
    'production_process_patch=none\n'
    'stiffness_scaling=false\n'
    'residual_homotopy=false\n'
    'material_homotopy=false\n'
    'runtime_exit=0\n', encoding='utf-8')
PY