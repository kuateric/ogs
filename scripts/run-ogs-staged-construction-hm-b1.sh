#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-hm-b1

git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-hm-b1
cd ogs-hm-b1
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# Runtime evidence only: instrument the existing canonical HM assembler so the
# executed log proves when a coupled element participates in assembly. The
# assembled call contains mechanics, Biot coupling, storage and Darcy blocks.
python3 - <<'PY'
from pathlib import Path
p = Path('ProcessLib/HydroMechanics/HydroMechanicsFEM-impl.h')
text = p.read_text(encoding='utf-8')
anchor = '''{
    assert(local_x.size() == pressure_size + displacement_size);
'''
replacement = '''{
    INFO("HM-B1 coupled assembly element {:d} at t = {:g}", _element.getID(), t);
    assert(local_x.size() == pressure_size + displacement_size);
'''
if text.count(anchor) != 1:
    raise RuntimeError('unexpected HydroMechanics assembleWithJacobian entry')
p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
PY

git diff --check

cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=HydroMechanics'
cmake --build --preset release --target ProcessLib HydroMechanics ogs --parallel 2

# Start from the canonical HM deactivation regression and extend the horizon so
# the material IDs deactivated over [0,1] are assembled again after the interval.
cp -a Tests/Data/HydroMechanics/HydraulicDeactivation hm-b1-case
python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET
p = Path('hm-b1-case/simHM_deactivate_H.prj')
tree = ET.parse(p)
root = tree.getroot()
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
# Preserve exact deactivation interval [0,1]; t=2 is therefore reactivated.
tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p hm-b1-out
set +e
"$OGS_BIN" -o hm-b1-out hm-b1-case/simHM_deactivate_H.prj > hm-b1.log 2>&1
rc=$?
set -e
cat hm-b1.log
if [ "$rc" -ne 0 ]; then
  echo "HM-B1 canonical coupled deactivation/reactivation probe failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' hm-b1.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('hm-b1.log').read_text(errors='replace')
pat = re.compile(r'HM-B1 coupled assembly element (\d+) at t = ([-+0-9.eE]+)')
records = [(int(e), float(t)) for e, t in pat.findall(log)]
if not records:
    raise RuntimeError('no HM-B1 coupled assembly evidence found')
by_time = {}
for e, t in records:
    by_time.setdefault(round(t, 12), set()).add(e)
# The canonical case deactivates material IDs 1 and 3 on the pressure variable
# during [0,1]. The key runtime requirement for this B1 probe is that the active
# coupled assembly topology changes and that additional elements return after
# the support interval, proving the generic active-domain machinery reaches HM.
active_t1 = by_time.get(1.0, set())
active_t2 = by_time.get(2.0, set())
if not active_t1 or not active_t2:
    raise RuntimeError(f'missing HM assembly snapshots: t1={len(active_t1)} t2={len(active_t2)}')
if not (active_t2 - active_t1):
    raise RuntimeError(
        f'expected reactivated HM elements after deactivation interval; '
        f't1={sorted(active_t1)}, t2={sorted(active_t2)}')
Path('../hm-b1-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B1_canonical_coupled_deactivation_reactivation_probe\n'
    f'active_elements_t1={sorted(active_t1)}\n'
    f'active_elements_t2={sorted(active_t2)}\n'
    f'reactivated_elements={sorted(active_t2-active_t1)}\n'
    'physical_time_horizon=2.0\n'
    'runtime_exit=0\n',
    encoding='utf-8')
PY
