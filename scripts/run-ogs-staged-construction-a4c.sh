#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-a4c-e2e
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-a4c-e2e
cd ogs-a4c-e2e
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
cd ..

stages='r0 r2b r2c r2d r2e r2f r2g r2h r2i r2j r2k r2k-f01 r2l r3a r3b r3c r3d r3e r3f r3g r3h r3i a0 a1 a3 a4 a4b a4c a4d'
for s in $stages; do cp "scripts/ogs-staged-construction-${s}.py" ogs-a4c-e2e/; done
cd ogs-a4c-e2e
for s in $stages; do python3 "ogs-staged-construction-${s}.py"; done
git diff --check

cmake --preset release --fresh -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=SmallDeformation'
cmake --build --preset release --target ProcessLib SmallDeformation ogs --parallel 2

python3 - <<'PY'
from pathlib import Path
import shutil

root = Path.cwd()
src = root / 'Tests/Data/Mechanics/Excavation'
dst = root / 'a4c-strong-B'
shutil.copytree(src, dst, dirs_exist_ok=True)
p = dst / 'time_linear_excavation.prj'
text = p.read_text(encoding='latin-1')

old = '''            <constitutive_relation id="0,1">
                <type>LinearElasticIsotropic</type>
                <youngs_modulus>E</youngs_modulus>
                <poissons_ratio>nu</poissons_ratio>
            </constitutive_relation>'''
if text.count(old) != 1:
    raise RuntimeError('unexpected canonical constitutive relation')
relation_a = '''            <constitutive_relation id="0,1">
                <type>MFront</type>
                <behaviour>MohrCoulombAbboSloan</behaviour>
                <material_properties>
                    <material_property name="YoungModulus" parameter="E_A"/>
                    <material_property name="PoissonRatio" parameter="nu"/>
                    <material_property name="Cohesion" parameter="MC_Cohesion"/>
                    <material_property name="FrictionAngle" parameter="MC_FrictionAngle"/>
                    <material_property name="DilatancyAngle" parameter="MC_DilatancyAngle"/>
                    <material_property name="TransitionAngle" parameter="MC_TransitionAngle"/>
                    <material_property name="TensionCutOffParameter" parameter="MC_TensionCutOff"/>
                </material_properties>
            </constitutive_relation>'''
relation_b = '''            <constitutive_relation id="2">
                <type>MFront</type>
                <behaviour>MohrCoulombAbboSloan</behaviour>
                <material_properties>
                    <material_property name="YoungModulus" parameter="E_B"/>
                    <material_property name="PoissonRatio" parameter="nu"/>
                    <material_property name="Cohesion" parameter="MC_Cohesion"/>
                    <material_property name="FrictionAngle" parameter="MC_FrictionAngle"/>
                    <material_property name="DilatancyAngle" parameter="MC_DilatancyAngle"/>
                    <material_property name="TransitionAngle" parameter="MC_TransitionAngle"/>
                    <material_property name="TensionCutOffParameter" parameter="MC_TensionCutOff"/>
                </material_properties>
            </constitutive_relation>'''
text = text.replace(old, relation_a + '\n' + relation_b)

medium_tag = '<medium id="0, 1">'
if text.count(medium_tag) != 1:
    raise RuntimeError('unexpected canonical medium layout')
text = text.replace(medium_tag, '<medium id="0, 1, 2">')

marker = '            <specific_body_force>0 0</specific_body_force>'
if text.count(marker) != 1:
    raise RuntimeError('unexpected process layout')
text = text.replace(marker, marker + '\n            <reference_temperature>T_ref</reference_temperature>')
params = '''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>E_A</name><type>Constant</type><value>4000e6</value></parameter>
        <parameter><name>E_B</name><type>Constant</type><value>1000e6</value></parameter>
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>5e6</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''
if text.count('    </parameters>') != 1:
    raise RuntimeError('unexpected parameters layout')
text = text.replace('    </parameters>', params + '    </parameters>')
material_tag = '                    <material_ids>0</material_ids>'
if text.count(material_tag) != 2:
    raise RuntimeError('expected two canonical deactivated-subdomain material tags')
text = text.replace(material_tag, material_tag + '\n                    <activation_material_id>2</activation_material_id>')
if '<t_end>8</t_end>' not in text:
    raise RuntimeError('canonical full backfill horizon missing')
p.write_text(text, encoding='latin-1')
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
mkdir -p a4c-strong-B-out
set +e
"$OGS_BIN" -o a4c-strong-B-out a4c-strong-B/time_linear_excavation.prj > a4c-strong-B.log 2>&1
rc=$?
set -e
cat a4c-strong-B.log
if [ "$rc" -ne 0 ]; then
    echo "A4C strong-contrast run failed with rc=$rc" >&2
    exit "$rc"
fi

grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' a4c-strong-B.log
grep -q 'Staged construction transition completed for process' a4c-strong-B.log
! grep -q 'MFront: integration failed' a4c-strong-B.log

python3 - <<'PY'
from pathlib import Path
import re
log = Path('a4c-strong-B.log').read_text(errors='replace')
number = r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?'
times = [float(m.group(1)) for m in re.finditer(r'Time:\s*(' + number + r')', log)]
if not times or max(times) < 8.0 - 1e-12:
    raise RuntimeError(f'A4C full backfill horizon not reached; max={max(times) if times else None}')
trials = re.findall(r'Staged construction (?:pre-solve )?trial for process.*?lambda\s*=\s*(' + number + r')', log)
completed = log.count('Staged construction transition completed for process')
if completed < 2:
    raise RuntimeError(f'A4C expected removal and activation continuations; completed={completed}')
if not re.search(r'Staged construction pre-solve trial for process.*?physical time t\s*=\s*1\.2', log):
    raise RuntimeError('A4D activation pre-solve trial at t=1.2 not observed')
if not re.search(r'Staged construction trial for process.*?unchanged physical time t\s*=\s*1\.2', log):
    raise RuntimeError('A4C activation continuation after pre-solve trial at t=1.2 not observed')
Path('staged-a4c-evidence.txt').write_text(
    f'upstream_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n'
    f'gate=A4D_strong_contrast_pre_solve_controlled_activation_e2e\n'
    f'max_time={max(times)}\n'
    f'material_A=MFront/MohrCoulombAbboSloan/E=4e9\n'
    f'material_B=MFront/MohrCoulombAbboSloan/E=1e9\n'
    f'activation_material_id=2\n'
    f'placement_reference=stress_free_displacement_at_birth\n'
    f'pre_solve_activation_trial=1\n'
    f'construction_trials={len(trials)}\n'
    f'construction_transition_completed={completed}\n'
    f'mfront_integration_failure=0\n'
    f'full_backfill_horizon_reached=1\n',
    encoding='utf-8')
PY
