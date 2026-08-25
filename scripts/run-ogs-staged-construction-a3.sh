#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-upstream
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-upstream
cd ogs-upstream
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
cd ..

stages='r0 r2b r2c r2d r2e r2f r2g r2h r2i r2j r2k r2k-f01 r2l r3a r3b r3c r3d r3e r3f r3g r3h r3i a0 a1 a3'
for s in $stages; do cp "scripts/ogs-staged-construction-${s}.py" ogs-upstream/; done
cd ogs-upstream
for s in $stages; do python3 "ogs-staged-construction-${s}.py"; done
git diff --check

cmake --preset release -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=SmallDeformation'
cmake --build --preset release --target ProcessLib SmallDeformation ogs --parallel 2

python3 - <<'PY'
from pathlib import Path
import shutil

root = Path.cwd()
src = root / 'Tests/Data/Mechanics/Excavation'
for name, activation_id in [('a3-control-A', 0), ('a3-test-B', 1)]:
    dst = root / name
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
    relation0 = '''            <constitutive_relation id="0">
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
    relation1 = '''            <constitutive_relation id="1">
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
    text = text.replace(old, relation0 + '\n' + relation1)
    marker = '            <specific_body_force>0 0</specific_body_force>'
    if text.count(marker) != 1:
        raise RuntimeError('unexpected process layout')
    text = text.replace(marker, marker + '\n            <reference_temperature>T_ref</reference_temperature>')
    params = '''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>E_A</name><type>Constant</type><value>4000e6</value></parameter>
        <parameter><name>E_B</name><type>Constant</type><value>3800e6</value></parameter>
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
    text = text.replace(material_tag, material_tag + f'\n                    <activation_material_id>{activation_id}</activation_material_id>')
    if '<t_end>8</t_end>' not in text:
        raise RuntimeError('canonical full backfill horizon missing')
    p.write_text(text, encoding='latin-1')

control = (root/'a3-control-A/time_linear_excavation.prj').read_text(encoding='latin-1')
test = (root/'a3-test-B/time_linear_excavation.prj').read_text(encoding='latin-1')
if control.replace('<activation_material_id>0</activation_material_id>', '<activation_material_id>X</activation_material_id>') != test.replace('<activation_material_id>1</activation_material_id>', '<activation_material_id>X</activation_material_id>'):
    raise RuntimeError('A3 control and test differ in more than activation_material_id')
PY

OGS_BIN="$(find "${GITHUB_WORKSPACE:-$PWD/..}/build/release" -type f -name ogs -perm -111 | head -n1)"
test -n "$OGS_BIN"
for case in a3-control-A a3-test-B; do
    mkdir -p "${case}-out"
    "$OGS_BIN" -o "${case}-out" "${case}/time_linear_excavation.prj" > "${case}.log" 2>&1
    grep -Eqi 'Simulation completed|OGS completed|simulation terminated successfully|OGS terminated successfully' "${case}.log"
    grep -q 'Staged construction transition completed for process' "${case}.log"
    ! grep -q 'MFront: integration failed' "${case}.log"
done

python3 - <<'PY'
from pathlib import Path
import hashlib, re

evidence = []
for case in ['a3-control-A', 'a3-test-B']:
    log = Path(case + '.log').read_text(errors='replace')
    times = [float(m.group(1)) for m in re.finditer(r'Time:\s*([0-9.eE+-]+)', log)]
    if not times or max(times) < 8.0 - 1e-12:
        raise RuntimeError(f'{case}: full backfill horizon not reached')
    files = sorted(Path(case + '-out').glob('*.vtu'))
    if not files:
        raise RuntimeError(f'{case}: no VTU output')
    final = files[-1]
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    evidence.append((case, max(times), final.name, digest))

if evidence[0][3] == evidence[1][3]:
    raise RuntimeError('A3 control and material-B activation produced identical final VTU; material reassignment not demonstrated')

Path('staged-a3-evidence.txt').write_text(
    '\n'.join(f'{case}:max_time={t}:final={name}:sha256={digest}' for case,t,name,digest in evidence) + '\n' +
    'control_activation_material_id=0\n' +
    'test_activation_material_id=1\n' +
    'material_A=MFront/MohrCoulombAbboSloan/E=4e9\n' +
    'material_B=MFront/MohrCoulombAbboSloan/E=3.8e9\n' +
    'final_vtu_different=1\n' +
    'fresh_state_contract=A1\n' +
    'scope_note=A3 proves material identity reassignment with a deliberately small constitutive contrast; large placement/load jumps are reserved for A4 controlled placement-state gate\n', encoding='utf-8')
PY
