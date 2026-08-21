#!/usr/bin/env bash
set -euo pipefail

: "${OGS_UPSTREAM_SHA:=adf770974c7ee0435702fe617634d03d17ab7cb8}"
: "${OGS_UPSTREAM_URL:=https://gitlab.opengeosys.org/ogs/ogs.git}"

rm -rf ogs-upstream
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-upstream
cd ogs-upstream
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
test -f Tests/Data/Mechanics/Excavation/time_linear_excavation.prj
test -f Tests/Data/Mechanics/MohrCoulombAbboSloan/slope.prj
test -f MaterialLib/SolidModels/MFront/MohrCoulombAbboSloan.mfront

cmake --preset release \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  -DOGS_USE_MFRONT=ON \
  '-DOGS_BUILD_PROCESSES=SmallDeformation;HydroMechanics;ThermoRichardsMechanics'
cmake --build --preset release --parallel 2

mkdir -p actplas-evidence/controls actplas-evidence/logs actplas-evidence/generated-prj
OGS_BIN="$(find "$(pwd)/../build/release" -type f -name ogs -perm -111 2>/dev/null | head -n1 || true)"
if [[ -z "$OGS_BIN" ]]; then
  OGS_BIN="$(find "$(pwd)/../build" -type f -name ogs -perm -111 2>/dev/null | head -n1 || true)"
fi
test -n "$OGS_BIN"
OGS_BIN="$(readlink -f "$OGS_BIN")"
printf 'ogs_binary=%s\n' "$OGS_BIN" > actplas-evidence/runtime.txt

printf 'control\texit_code\n' > actplas-evidence/controls.tsv
run_control() {
  local name="$1" dir="$2" prj="$3" outdir log rc
  outdir="$(pwd)/actplas-evidence/controls/out_${name}"
  log="$(pwd)/actplas-evidence/controls/${name}.log"
  mkdir -p "$outdir"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" "$prj") >"$log" 2>&1
  rc=$?
  set -e
  printf '%s\t%s\n' "$name" "$rc" | tee -a actplas-evidence/controls.tsv
}
run_control SM_ELASTIC_EXCAVATION Tests/Data/Mechanics/Excavation time_linear_excavation.prj
run_control SM_MC_SLOPE Tests/Data/Mechanics/MohrCoulombAbboSloan slope.prj

python3 - <<'PY'
import pathlib, re, shutil
root = pathlib.Path.cwd()
src = root / 'Tests/Data/Mechanics/Excavation'
cases = root / 'actplas-cases'
cases.mkdir(exist_ok=True)
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
params = '''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>5e6</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''
deact = cases / 'SM_MC_DEACT'
shutil.copytree(src, deact, dirs_exist_ok=True)
p = deact / 'time_linear_excavation.prj'
text = p.read_text(encoding='latin-1')
if text.count(old) != 1:
    raise RuntimeError('expected exactly one elastic constitutive relation')
text = text.replace(old, new)
marker = '            <specific_body_force>0 0</specific_body_force>'
if text.count(marker) != 1:
    raise RuntimeError('unexpected process layout')
text = text.replace(marker, marker + '\n            <reference_temperature>T_ref</reference_temperature>')
if text.count('    </parameters>') != 1:
    raise RuntimeError('unexpected parameters layout')
text = text.replace('    </parameters>', params + '    </parameters>')
p.write_text(text, encoding='latin-1')
nodeact = cases / 'SM_MC_NO_DEACT'
shutil.copytree(deact, nodeact, dirs_exist_ok=True)
p2 = nodeact / 'time_linear_excavation.prj'
text2 = p2.read_text(encoding='latin-1')
text2, n = re.subn(r'\s*<deactivated_subdomains>.*?</deactivated_subdomains>', '', text2, count=1, flags=re.S)
if n != 1:
    raise RuntimeError('expected exactly one deactivated_subdomains block')
p2.write_text(text2, encoding='latin-1')
(root/'actplas-evidence'/'generated-prj-summary.txt').write_text(
    'SM_MC_DEACT = exact upstream excavation with constitutive relation changed to MFront MohrCoulombAbboSloan; deactivation preserved\n'
    'SM_MC_NO_DEACT = identical project with deactivated_subdomains removed\n', encoding='utf-8')
PY

printf 'case\texit_code\tsuccess_marker\tnonlinear_failure_marker\n' > actplas-evidence/sm-r01.tsv
run_case() {
  local name="$1" dir outdir log rc success nlfail
  dir="actplas-cases/$name"
  outdir="$(pwd)/actplas-evidence/out_${name}"
  log="$(pwd)/actplas-evidence/logs/${name}.log"
  mkdir -p "$outdir"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1
  rc=$?
  set -e
  if grep -Eqi 'simulation terminated successfully|OGS terminated successfully|Time step.*accepted' "$log"; then success=yes; else success=no; fi
  if grep -Eqi 'Newton.*fail|nonlinear.*fail|did not converge|maximum number of iterations|time step.*fail' "$log"; then nlfail=yes; else nlfail=no; fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$success" "$nlfail" | tee -a actplas-evidence/sm-r01.tsv
}
run_case SM_MC_NO_DEACT
run_case SM_MC_DEACT

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' \
  "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cp actplas-cases/SM_MC_NO_DEACT/time_linear_excavation.prj actplas-evidence/generated-prj/SM_MC_NO_DEACT.prj
cp actplas-cases/SM_MC_DEACT/time_linear_excavation.prj actplas-evidence/generated-prj/SM_MC_DEACT.prj
cat actplas-evidence/controls.tsv
cat actplas-evidence/sm-r01.tsv
