#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-hm-b5
cd "$(dirname "$0")/.."
ROOT="$PWD"
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b5
cd ogs-hm-b5
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# Compose only the already-authoritative lifecycle dependencies and HM B2-B4.
python3 "$ROOT/scripts/ogs-staged-construction-r0.py"
python3 "$ROOT/scripts/ogs-staged-construction-r2g.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b2.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b3.py"
python3 "$ROOT/scripts/ogs-staged-construction-hm-b4.py"
git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2

cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b5-case
python3 - <<'PY'
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('hm-b5-case/simHM_deactivate_H.prj')
tree = ET.parse(p)
root = tree.getroot()
variables = root.findall('./process_variables/process_variable')
by_name = {pv.findtext('name').strip(): pv for pv in variables if pv.findtext('name')}
pressure = by_name['pressure']
displacement = by_name['displacement']
pressure_ds = pressure.find('deactivated_subdomains')
if pressure_ds is None or displacement.find('deactivated_subdomains') is not None:
    raise RuntimeError('unexpected canonical HM deactivation layout')
ic = displacement.find('initial_condition')
insert_at = list(displacement).index(ic) + 1 if ic is not None else len(displacement)
displacement.insert(insert_at, deepcopy(pressure_ds))

# HM-B5 is the first deliberately loaded coupled-birth gate. Use a small but
# non-zero gravity-like body force so the topology change creates a measurable
# construction disequilibrium while remaining deterministic. The local HM
# operator, constitutive law, Darcy/storage/Biot terms remain fully physical.
b = root.find('./processes/process/specific_body_force')
if b is None:
    raise RuntimeError('specific_body_force not found')
b.text = '0 -0.1'

# Keep pressure placement/BCs uniform so B5 isolates loaded mechanical/HM
# equilibrium restoration rather than introducing a hydraulic gradient.
for par in root.findall('./parameters/parameter'):
    if par.findtext('name') == 'InitialPressure':
        par.find('values').text = '12345'
    if par.findtext('name') == 'zero':
        par.find('values').text = '12345'

ts = root.find('./time_loop/processes/process/time_stepping')
if ts is None:
    raise RuntimeError('time stepping not found')
ts.find('t_end').text = '2.0'
pair = ts.find('./timesteps/pair')
pair.find('repeat').text = '2'
pair.find('delta_t').text = '1.0'
tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$ROOT}/build/release" -type f -name ogs -perm -111 | head -n1)"
if [ -z "$OGS_BIN" ]; then
  OGS_BIN="$(find "$ROOT/build/release" -type f -name ogs -perm -111 | head -n1)"
fi
test -n "$OGS_BIN"
mkdir -p hm-b5-out
set +e
"$OGS_BIN" -o hm-b5-out hm-b5-case/simHM_deactivate_H.prj > hm-b5.log 2>&1
rc=$?
set -e
cat hm-b5.log
if [ "$rc" -ne 0 ]; then
  echo "HM-B5 loaded coupled birth equilibrium failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b5.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('hm-b5.log').read_text(errors='replace')

fresh = sorted(set(int(x) for x in re.findall(
    r'HM-B3 fresh coupled birth state initialized for element (\d+)', log)))
placements = [(int(e), float(p)) for e,p in re.findall(
    r'HM-B4 placement state captured for element (\d+): p_L0=([-+0-9.eE]+)', log)]
placement_ids = sorted(set(e for e,_ in placements))
if len(fresh) != 6 or len(placement_ids) != 6:
    raise RuntimeError(f'expected six loaded newborn HM elements; fresh={fresh}, placement={placement_ids}')
if any(abs(p - 12345.0) > 1e-8 for _,p in placements):
    raise RuntimeError(f'wrong HM-B5 explicit p_L0: {placements}')

# Prove this was a genuinely loaded equilibrium restoration rather than the
# zero-load B2-B4 state gates. OGS reports displacement as component 2 in this
# canonical 2D HM ordering. Require a non-zero Newton correction at t=2.
segments = re.findall(r'Time step #2 started\.(.*?)(?=Time step #|The whole computation)', log, re.S)
if not segments:
    raise RuntimeError('missing t=2 solve evidence')
dx = [float(v) for v in re.findall(
    r'Convergence criterion, component 2: \|dx\|=([-+0-9.eE]+)', segments[0])]
if not dx or max(abs(v) for v in dx) <= 1e-12:
    raise RuntimeError(f'loaded birth produced no measurable displacement correction: {dx}')

m = re.search(r'The whole computation of the time stepping took (\d+) steps, in which\s+the accepted steps are (\d+), and the rejected steps are (\d+)', log)
if not m:
    raise RuntimeError('missing time-step summary')
total, accepted, rejected = map(int, m.groups())
if total != 2 or accepted != 2 or rejected != 0:
    raise RuntimeError(f'unexpected physical-time stepping: total={total}, accepted={accepted}, rejected={rejected}')

Path('../hm-b5-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B5_loaded_coupled_birth_equilibrium\n'
    f'fresh_birth_elements={fresh}\n'
    f'placement_elements={placement_ids}\n'
    'explicit_p_L0=12345\n'
    'specific_body_force=0,-0.1\n'
    f'max_t2_displacement_newton_correction={max(abs(v) for v in dx):.17g}\n'
    'full_physical_operator_at_birth=true\n'
    'stress_free_mechanical_birth=true\n'
    'physical_time_steps=2\n'
    'extra_construction_time_steps=0\n'
    'runtime_exit=0\n', encoding='utf-8')
PY
