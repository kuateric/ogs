#!/usr/bin/env bash
set -Eeuxo pipefail

: "${OGS_UPSTREAM_URL:=https://github.com/Helmholtz-UFZ/ogs.git}"
: "${OGS_UPSTREAM_SHA:=adf770974c7ee0435702fe617634d03d17ab7cb8}"
: "${CPM_SOURCE_CACHE:=$PWD/.cpm-cache}"
export CPM_SOURCE_CACHE

A2_STAGE=initialization
rm -f a2-failure.txt
trap 'rc=$?; { printf "stage=%s\n" "$A2_STAGE"; printf "exit_code=%s\n" "$rc"; printf "line=%s\n" "$LINENO"; printf "command=%s\n" "$BASH_COMMAND"; if test -f ogs-upstream/staged-a2.log; then printf "log_tail_begin=1\n"; tail -n 120 ogs-upstream/staged-a2.log; printf "log_tail_end=1\n"; fi; } > a2-failure.txt; exit "$rc"' ERR

A2_STAGE=canonical_checkout
rm -rf ogs-upstream

git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-upstream
(
  cd ogs-upstream
  git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
  git checkout --detach FETCH_HEAD
  test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
)

A2_STAGE=apply_staged_construction_patches
for s in r0 r2b r2c r2d r2e r2f r2g r2h r2i r2j r2k r2k-f01 r2l r3a r3b r3c r3d r3e r3f r3g r3h r3i a0 a1; do
  cp "scripts/ogs-staged-construction-${s}.py" ogs-upstream/
done
(
  cd ogs-upstream
  for s in r0 r2b r2c r2d r2e r2f r2g r2h r2i r2j r2k r2k-f01 r2l r3a r3b r3c r3d r3e r3f r3g r3h r3i a0 a1; do
    python3 "ogs-staged-construction-${s}.py"
  done
  grep -q 'initializeActivationPlacementState' ProcessLib/SmallDeformation/LocalAssemblerInterface.h
  grep -q 'newly_activated_element_ids' ProcessLib/SmallDeformation/SmallDeformationProcess.cpp
  git diff --check
)

A2_STAGE=configure_mfront_small_deformation
cmake -S ogs-upstream -B build/a2 -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  -DOGS_USE_MFRONT=ON \
  -DOGS_BUILD_PROCESSES=SmallDeformation

A2_STAGE=build_mfront_small_deformation
cmake --build build/a2 --target ProcessLib SmallDeformation ogs --parallel 2

A2_STAGE=prepare_plastic_backfill_case
python3 - <<'PY'
from pathlib import Path
import shutil
src = Path('ogs-upstream/Tests/Data/Mechanics/Excavation')
dst = Path('ogs-upstream/staged-a2-case')
shutil.copytree(src, dst, dirs_exist_ok=True)
p = dst / 'time_linear_excavation.prj'
text = p.read_text(encoding='latin-1')
old = '''            <constitutive_relation id="0,1">
                <type>LinearElasticIsotropic</type>
                <youngs_modulus>E</youngs_modulus>
                <poissons_ratio>nu</poissons_ratio>
            </constitutive_relation>'''
if old not in text:
    old = '''            <constitutive_relation id="0,1">
                          <type>LinearElasticIsotropic</type>
                          <youngs_modulus>E</youngs_modulus>
                          <poissons_ratio>nu</poissons_ratio>
                      </constitutive_relation>'''
new = '''            <constitutive_relation id="0,1">
                <type>MFront</type>
                <behaviour>MohrCoulombAbboSloan</behaviour>
                <material_properties>
                    <material_property name="YoungModulus" parameter="E"/>
                    <material_property name="PoissonRatio" parameter="nu"/>
                    <material_property name="Cohesion" parameter="MC_Cohesion"/>
                    <material_property name="FrictionAngle" parameter="MC_FrictionAngle"/>
                    <material_property name="DilatancyAngle" parameter="MC_DilatancyAngle"/>
                    <material_property name="TransitionAngle" parameter="MC_TransitionAngle"/>
                    <material_property name="TensionCutOffParameter" parameter="MC_TensionCutOff"/>
                </material_properties>
            </constitutive_relation>'''
if text.count(old) != 1:
    raise RuntimeError('expected one elastic constitutive relation')
text = text.replace(old, new)
marker = '            <specific_body_force>0 0</specific_body_force>'
if text.count(marker) != 1:
    raise RuntimeError('unexpected process layout')
text = text.replace(marker, marker + '\n            <reference_temperature>T_ref</reference_temperature>')
params = '''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>5e6</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''
if text.count('    </parameters>') != 1:
    raise RuntimeError('unexpected parameters layout')
text = text.replace('    </parameters>', params + '    </parameters>')
if '<t_end>8</t_end>' not in text:
    raise RuntimeError('canonical backfill horizon missing')
p.write_text(text, encoding='latin-1')
PY

A2_STAGE=execute_plastic_excavation_backfill
OGS_BIN="$(find build/a2 -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p ogs-upstream/staged-a2-out
set +e
"$OGS_BIN" -o ogs-upstream/staged-a2-out ogs-upstream/staged-a2-case/time_linear_excavation.prj > ogs-upstream/staged-a2.log 2>&1
rc=$?
set -e
cat ogs-upstream/staged-a2.log
if test "$rc" -ne 0; then
  false
fi

A2_STAGE=validate_plastic_backfill_evidence
grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' ogs-upstream/staged-a2.log
grep -q 'Staged construction transition completed for process' ogs-upstream/staged-a2.log
! grep -q 'MFront: integration failed' ogs-upstream/staged-a2.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('ogs-upstream/staged-a2.log').read_text(errors='replace')
times = [float(m.group(1)) for m in re.finditer(r'Time:\s*([0-9.eE+-]+)', log)]
if not times or max(times) < 8.0 - 1e-12:
    raise RuntimeError(f'full backfill horizon not reached: {max(times) if times else None}')
if 'MFront: integration failed' in log:
    raise RuntimeError('MFront integration failure during backfill')
Path('ogs-upstream/staged-a2-evidence.txt').write_text(
    f'max_time={max(times)}\nfull_backfill_horizon_reached=1\nmfront_integration_failure=0\n',
    encoding='utf-8')
PY

A2_STAGE=complete
trap - ERR
rm -f a2-failure.txt
