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
# executed log proves when a coupled element participates in assembly. This B1
# gate intentionally applies NO staged-construction HM fix. It freezes the
# upstream limitation that a pressure-only deactivated_subdomains declaration
# does not shrink the monolithic HM operator while displacement is unrestricted.
# HM-B2 is the separate positive gate for the corrected synchronized lifecycle.
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
# the pressure-only support interval [0,1] can be compared to t=2. The purpose
# here is to prove the unchanged canonical coupled-active-domain limitation,
# not to validate the HM-B2 fix.
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
  echo "HM-B1 canonical coupled limitation probe failed to execute with rc=$rc" >&2
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
active_t1 = by_time.get(1.0, set())
active_t2 = by_time.get(2.0, set())
if not active_t1 or not active_t2:
    raise RuntimeError(f'missing HM assembly snapshots: t1={len(active_t1)} t2={len(active_t2)}')

# Canonical upstream finding: pressure alone owns deactivated_subdomains, while
# displacement is unrestricted. The current Process active-set union/early-return
# semantics therefore leave the entire monolithic HM assembly active. Freeze this
# as an expected negative reference. If upstream behavior changes, this gate must
# fail so B2 can be revisited rather than silently becoming redundant.
if active_t1 != active_t2:
    raise RuntimeError(
        'canonical HM coupled-active-domain behavior changed unexpectedly: '
        f't1={sorted(active_t1)}, t2={sorted(active_t2)}')
if len(active_t1) != 15:
    raise RuntimeError(
        'expected all 15 canonical HM elements to remain assembled under the '
        f'pressure-only restriction, got {sorted(active_t1)}')

Path('../hm-b1-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=HM_B1_canonical_coupled_deactivation_limitation\n'
    f'active_elements_t1={sorted(active_t1)}\n'
    f'active_elements_t2={sorted(active_t2)}\n'
    'canonical_pressure_only_deactivation_does_not_shrink_monolithic_operator=true\n'
    'corrected_positive_gate=HM_B2\n'
    'physical_time_horizon=2.0\n'
    'runtime_exit=0\n',
    encoding='utf-8')
PY
