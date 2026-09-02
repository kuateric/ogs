#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/ufz/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-rm-r1
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-rm-r1
cd ogs-rm-r1
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"

# R1 follows the established OGS process-wide active-domain mechanism already
# exercised by HM-B2. No numerical continuation, stiffness scaling, residual
# homotopy, or material homotopy is introduced. The canonical RM A2 benchmark
# already declares the same deactivated material subdomain for pressure and
# displacement; this gate changes only the lifecycle schedule to a reversible
# interval and instruments the real monolithic RM local assembler.
python3 - <<'PY'
from pathlib import Path
p = Path('ProcessLib/RichardsMechanics/RichardsMechanicsFEM-impl.h')
text = p.read_text(encoding='utf-8')
anchor = '''void RichardsMechanicsLocalAssembler<ShapeFunctionDisplacement,\n                                     ShapeFunctionPressure, DisplacementDim>::\n    assembleWithJacobian(double const t, double const dt,\n                         std::vector<double> const& local_x,\n                         std::vector<double> const& local_x_prev,\n                         std::vector<double>& local_rhs_data,\n                         std::vector<double>& local_Jac_data)\n{\n'''
replacement = anchor + '''    INFO("RM-R1 coupled assembly element {} at t = {:g}", this->element_.getID(), t);\n'''
if text.count(anchor) != 1:
    raise RuntimeError('unexpected RichardsMechanics assembleWithJacobian entry')
p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
PY

git diff --check
cmake --preset release --fresh \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  '-DOGS_BUILD_PROCESSES=RichardsMechanics'
cmake --build --preset release --target ProcessLib RichardsMechanics ogs --parallel 2

cp -a Tests/Data/RichardsMechanics rm-r1-case
python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

p = Path('rm-r1-case/A2.prj')
tree = ET.parse(p)
root = tree.getroot()
variables = {pv.findtext('name').strip(): pv for pv in root.findall('./process_variables/process_variable')}
for name in ('pressure', 'displacement'):
    pv = variables.get(name)
    if pv is None:
        raise RuntimeError(f'missing RM process variable {name}')
    ds = pv.find('deactivated_subdomains/deactivated_subdomain')
    if ds is None or (ds.findtext('material_ids') or '').strip() != '1':
        raise RuntimeError(f'canonical RM A2 does not expose expected MaterialID=1 lifecycle for {name}')
    for tag in ('time_curve', 'line_segment', 'boundary_parameter'):
        x = ds.find(tag)
        if x is not None:
            ds.remove(x)
    ti = ET.Element('time_interval')
    ET.SubElement(ti, 'start').text = '2160'
    ET.SubElement(ti, 'end').text = '4320'
    ds.insert(0, ti)

# Preserve the canonical A2 physical parameters unchanged. Use only the first
# four canonical time increments so the lifecycle probe remains compact while
# retaining the benchmark's established numerical time scale:
# 0 -> 0.01 -> 2160 -> 4320 -> 4334 s.
ts = root.find('./time_loop/processes/process/time_stepping')
if ts is None:
    raise RuntimeError('missing RM time stepping')
for child in list(ts):
    if child.tag in {'t_end', 'timesteps'}:
        ts.remove(child)
ET.SubElement(ts, 't_end').text = '4334'
timesteps = ET.SubElement(ts, 'timesteps')
for dt in ('0.01', '2159.99', '2160', '14'):
    pair = ET.SubElement(timesteps, 'pair')
    ET.SubElement(pair, 'repeat').text = '1'
    ET.SubElement(pair, 'delta_t').text = dt

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p rm-r1-out
set +e
"$OGS_BIN" -o rm-r1-out rm-r1-case/A2.prj > rm-r1.log 2>&1
rc=$?
set -e
cat rm-r1.log
if [ "$rc" -ne 0 ]; then
  echo "RM-R1 runtime probe failed with rc=$rc" >&2
  exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' rm-r1.log
python3 - <<'PY'
from pathlib import Path
import re
log = Path('rm-r1.log').read_text(errors='replace')
pat = re.compile(r'RM-R1 coupled assembly element (\d+) at t = ([-+0-9.eE]+)')
by_time = {}
for e, t in pat.findall(log):
    by_time.setdefault(round(float(t), 8), set()).add(int(e))
for t in (0.01, 2160.0, 4320.0, 4334.0):
    if t not in by_time:
        raise RuntimeError(f'missing RM-R1 assembly snapshot at t={t}; available={sorted(by_time)}')
a0, a1, a2, a3 = by_time[0.01], by_time[2160.0], by_time[4320.0], by_time[4334.0]
if not a0:
    raise RuntimeError('RM-R1 missing pre-construction active domain')
inactive_candidates = [s for s in (a1, a2) if s < a3]
if not inactive_candidates:
    raise RuntimeError(f'RM domain did not shrink: t2160={len(a1)} t4320={len(a2)} t4334={len(a3)}')
inactive = min(inactive_candidates, key=len)
reactivated = a3 - inactive
if not reactivated:
    raise RuntimeError('RM-R1 no reactivated elements evidenced')
Path('../rm-r1-evidence.txt').write_text(
    'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    'gate=RM_R1_synchronized_pressure_displacement_domain_lifecycle\n'
    f'active_elements_t0.01={sorted(a0)}\n'
    f'active_elements_t2160={sorted(a1)}\n'
    f'active_elements_t4320={sorted(a2)}\n'
    f'active_elements_t4334={sorted(a3)}\n'
    f'reactivated_elements={sorted(reactivated)}\n'
    'pressure_and_displacement_declaration=synchronized\n'
    'canonical_a2_physics=unchanged\n'
    'canonical_time_increments=0.01,2159.99,2160,14\n'
    'runtime_exit=0\n', encoding='utf-8')
print(Path('../rm-r1-evidence.txt').read_text())
PY
