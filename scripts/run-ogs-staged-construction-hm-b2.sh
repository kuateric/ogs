#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-hm-b2
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b2
cd ogs-hm-b2
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# HM-B2 is an algebraic coupled-lifecycle gate, not yet the loaded excavation
# gate.  The upstream HydraulicDeactivation case was designed to deactivate the
# hydraulic field only while retaining its mechanical skeleton.  Mirroring that
# restriction onto displacement under gravity changes the physics into an
# unsupported excavation problem and obscures whether the coupled active-domain
# machinery itself is correct.  Established staged-construction implementations
# separate these concerns: first define which elements/DOFs are active, then
# solve the construction-induced out-of-balance force.  Here we therefore set
# body force to zero and prove deterministic removal/re-entry of the complete HM
# local operator.  The following HM-B3 backfill gate will exercise loaded,
# stress-free birth and equilibrium restoration.

# Instrument the real monolithic HM local assembler.  Besides element IDs, log
# the actual local operator blocks so the gate proves that the active elements
# carry mechanics, Darcy and Biot coupling rather than merely visiting a code
# path.
python3 - <<'PY'
from pathlib import Path
p = Path('ProcessLib/HydroMechanics/HydroMechanicsFEM-impl.h')
text = p.read_text(encoding='utf-8')
anchor = '''{
    assert(local_x.size() == pressure_size + displacement_size);
'''
replacement = '''{
    INFO("HM-B2 coupled assembly element {:d} at t = {:g}", _element.getID(), t);
    assert(local_x.size() == pressure_size + displacement_size);
'''
if text.count(anchor) != 1:
    raise RuntimeError('unexpected HydroMechanics assembleWithJacobian entry')
text = text.replace(anchor, replacement, 1)

end_anchor = '''    local_rhs.template segment<displacement_size>(displacement_index)
        .noalias() += Kup * p;
}
'''
end_replacement = '''    local_rhs.template segment<displacement_size>(displacement_index)
        .noalias() += Kup * p;

    INFO("HM-B2 coupled blocks element {:d} at t = {:g}: mech={:g} darcy={:g} biot_up={:g} biot_pu={:g}",
         _element.getID(), t,
         local_Jac.template block<displacement_size, displacement_size>(
             displacement_index, displacement_index).norm(),
         laplace_p.norm(), Kup.norm(), Kpu.norm());
}
'''
if text.count(end_anchor) != 1:
    raise RuntimeError('unexpected HydroMechanics assembleWithJacobian tail')
p.write_text(text.replace(end_anchor, end_replacement, 1), encoding='utf-8')
PY

git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2

cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b2-case
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('hm-b2-case/simHM_deactivate_H.prj')
tree = ET.parse(p)
root = tree.getroot()

# Turn the upstream hydraulic-only restriction into an explicitly synchronized
# HM material-domain lifecycle declaration.  Both pressure and displacement
# describe the same material cluster, so isolated DOFs are constrained by the
# existing OGS DeactivatedSubdomainDirichlet machinery.
variables = root.findall('./process_variables/process_variable')
by_name = {}
for pv in variables:
    name = pv.findtext('name')
    if name:
        by_name[name.strip()] = pv
pressure = by_name.get('pressure')
displacement = by_name.get('displacement')
if pressure is None or displacement is None:
    raise RuntimeError(f'unexpected HM variables: {sorted(by_name)}')
pressure_ds = pressure.find('deactivated_subdomains')
if pressure_ds is None:
    raise RuntimeError('canonical pressure deactivated_subdomains not found')
if displacement.find('deactivated_subdomains') is not None:
    raise RuntimeError('canonical displacement unexpectedly already restricted')
ic = displacement.find('initial_condition')
insert_at = list(displacement).index(ic) + 1 if ic is not None else len(displacement)
displacement.insert(insert_at, deepcopy(pressure_ds))

# HM-B2 isolates active-domain algebra.  Removing a load-bearing cluster and its
# self-weight belongs to the next construction-equilibrium gate, not to this
# proof.  Zero body force makes the unchanged zero initial state an exact
# equilibrium while the full coupled local operator remains nonzero and is
# directly evidenced below.
b = root.find('./processes/process/specific_body_force')
if b is None:
    raise RuntimeError('specific_body_force not found')
b.text = '0 0'

# Run one interval with the coupled cluster inactive and one after reactivation.
ts = root.find('./time_loop/processes/process/time_stepping')
if ts is None:
    raise RuntimeError('time stepping not found')
t_end = ts.find('t_end')
pair = ts.find('./timesteps/pair')
if t_end is None or pair is None or pair.find('repeat') is None or pair.find('delta_t') is None:
    raise RuntimeError('unexpected canonical HM time stepping layout')
t_end.text = '2.0'
pair.find('repeat').text = '2'
pair.find('delta_t').text = '1.0'
tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p hm-b2-out
set +e
"$OGS_BIN" -o hm-b2-out hm-b2-case/simHM_deactivate_H.prj > hm-b2.log 2>&1
rc=$?
set -e
cat hm-b2.log
if [ "$rc" -ne 0 ]; then
  echo "HM-B2 coupled active-domain probe failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b2.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('hm-b2.log').read_text(errors='replace')
pat = re.compile(r'HM-B2 coupled assembly element (\d+) at t = ([-+0-9.eE]+)')
records = [(int(e), float(t)) for e, t in pat.findall(log)]
if not records:
    raise RuntimeError('no HM-B2 coupled assembly evidence found')
by_time = {}
for e, t in records:
    by_time.setdefault(round(t, 12), set()).add(e)
active_t1 = by_time.get(1.0, set())
active_t2 = by_time.get(2.0, set())
if not active_t1 or not active_t2:
    raise RuntimeError(f'missing HM-B2 assembly snapshots: t1={len(active_t1)} t2={len(active_t2)}')
if not active_t1 < active_t2:
    raise RuntimeError(
        f'coupled domain did not shrink and reactivate as required: '
        f't1={sorted(active_t1)}, t2={sorted(active_t2)}')

block_pat = re.compile(
    r'HM-B2 coupled blocks element (\d+) at t = ([-+0-9.eE]+): '
    r'mech=([-+0-9.eE]+) darcy=([-+0-9.eE]+) '
    r'biot_up=([-+0-9.eE]+) biot_pu=([-+0-9.eE]+)')
blocks = [(int(e), float(t), *(float(v) for v in vals))
          for e, t, *vals in block_pat.findall(log)]
if not blocks:
    raise RuntimeError('no HM-B2 coupled block evidence found')
for target_t in (1.0, 2.0):
    snapshot = [r for r in blocks if round(r[1], 12) == target_t]
    if not snapshot:
        raise RuntimeError(f'no coupled block snapshot at t={target_t}')
    # At least one active element must carry every nontrivial HM block present in
    # the canonical problem.  This guards against a vacuous zero-operator PASS.
    if max(r[2] for r in snapshot) <= 0.0:
        raise RuntimeError(f'zero mechanical operator at t={target_t}')
    if max(r[3] for r in snapshot) <= 0.0:
        raise RuntimeError(f'zero Darcy operator at t={target_t}')
    if max(r[4] for r in snapshot) <= 0.0 or max(r[5] for r in snapshot) <= 0.0:
        raise RuntimeError(f'zero Biot coupling operator at t={target_t}')

Path('../hm-b2-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B2_synchronized_coupled_domain_lifecycle\n'
    f'active_elements_t1={sorted(active_t1)}\n'
    f'active_elements_t2={sorted(active_t2)}\n'
    f'reactivated_elements={sorted(active_t2-active_t1)}\n'
    'pressure_and_displacement_lifecycle=synchronized\n'
    'mechanics_operator_evidenced=true\n'
    'darcy_operator_evidenced=true\n'
    'biot_coupling_evidenced=true\n'
    'body_force_for_lifecycle_gate=0\n'
    'physical_time_horizon=2.0\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
